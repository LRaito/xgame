from pathlib import Path

import click

from backend.config import RANKING_CSV_DIR, SEARCH_CSV_DIR, get_settings
from backend.database import ensure_data_dir, has_business_tables, init_db, make_engine


@click.group()
def cli() -> None:
    """x 后端管理命令。"""


@cli.command("init-db")
def init_db_cmd() -> None:
    """初始化一个全新的数据库；已有库请用 make upgrade 升级。"""
    settings = get_settings()
    ensure_data_dir(settings)
    engine = make_engine(settings)
    if has_business_tables(engine):
        click.echo("数据库已存在，结构升级请运行 make upgrade。", err=True)
        raise SystemExit(1)
    init_db(engine)
    click.echo("数据库已初始化。")


@cli.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="监听地址。")
@click.option("--port", default=8910, show_default=True, type=int, help="监听端口。")
@click.option(
    "--static-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="前端构建产物目录；给了就由后端顺带托管前端（Windows 包的做法）。",
)
@click.option(
    "--storage-root",
    type=click.Path(path_type=Path),
    default=None,
    help="数据根目录；不给就用默认的 <仓库>/data/storage。",
)
@click.option(
    "--runtime-root",
    type=click.Path(path_type=Path),
    default=None,
    help="运行时根目录（SQLite 库落它下面的 db/）；不给就与数据根相同。",
)
def serve_cmd(
    host: str,
    port: int,
    static_dir: Path | None,
    storage_root: Path | None,
    runtime_root: Path | None,
) -> None:
    """本机直跑一份「生产形态」的服务：单进程 uvicorn，可选地顺带托管前端。

    Docker 路线是 nginx + gunicorn；这条命令是给「没有 nginx 的本地场景」用的：
    开发时想看看真实形态、或者在 Windows 解压即用包里排查问题。`packaging/windows`
    的启动器用的是同一套环境变量，只是额外加了开浏览器、写 pid 之类的包装。

    环境变量必须在 import `backend.asgi` **之前**设好——那个模块在导入时就调
    `create_app()` 了，配置是那时读的（`get_settings()` 还带缓存）。
    """
    import os

    import uvicorn

    if storage_root is not None:
        os.environ["STORAGE_ROOT"] = str(storage_root.resolve())
    if runtime_root is not None:
        os.environ["RUNTIME_ROOT"] = str(runtime_root.resolve())
    if static_dir is not None:
        os.environ["STATIC_DIR"] = str(static_dir.resolve())

    click.echo(f"数据根：{os.environ.get('STORAGE_ROOT', '(默认)')}")
    click.echo(f"运行时根：{os.environ.get('RUNTIME_ROOT', '(同数据根)')}")
    click.echo(f"前端：{os.environ.get('STATIC_DIR', '(不托管，交给 nginx)')}")
    click.echo(f"访问：http://{host}:{port}")
    uvicorn.run("backend.asgi:app", host=host, port=port)


@cli.command("index")
@click.option("--csv-dir", type=click.Path(path_type=Path), default=None)
@click.option(
    "--out",
    "out_path",
    type=click.Path(path_type=Path),
    default=None,
    help="目标库路径；必须已由启动或 make upgrade 建好当前结构。",
)
@click.option(
    "--ranking-dir",
    type=click.Path(path_type=Path),
    default=None,
    help=f"游戏榜单 CSV 目录（默认 {RANKING_CSV_DIR.name}/）。",
)
def build_index_cmd(
    csv_dir: Path | None,
    out_path: Path | None,
    ranking_dir: Path | None,
) -> None:
    """全量构建游戏名录与游戏榜单，并同步两边的库存/榜单标记。

    每次都在已有的最新结构上整体重写数据；不改表结构、不建索引、不做结构迁移。
    结构不符（缺失/旧版本）时直接报错，请先启动服务或执行 make upgrade。
    执行前建议停止 api：本命令会写 app.db 的 in_ranking 标记。
    """
    # import 放在函数里：cli 的其它命令不该为了这个可选功能多拖依赖
    from backend.database import make_engine, read_db_version
    from backend.games.ranking_flags import FlagSyncError, refresh_all_flags
    from backend.games.search_index import (
        IndexBuildError,
        build_index,
        game_db_is_current,
    )
    from backend.system_config import LATEST_DB_VERSION

    settings = get_settings()
    ensure_data_dir(settings)

    if settings.database_path.is_file():
        version = read_db_version(make_engine(settings))
        if version != LATEST_DB_VERSION:
            raise click.ClickException(
                f"app.db 结构版本为 {version}，当前程序需要 {LATEST_DB_VERSION}；"
                "请先停止服务并执行 make upgrade。"
            )

    source = csv_dir or SEARCH_CSV_DIR
    target = out_path or settings.game_index_path
    ranking_source = ranking_dir or RANKING_CSV_DIR
    if not target.is_file():
        raise click.ClickException(
            f"game.db 尚未初始化：{target}；"
            "请先启动一次服务（或执行 make upgrade）创建空结构。"
        )
    if not game_db_is_current(target):
        raise click.ClickException(
            f"game.db 结构版本与当前程序不一致：{target}；"
            "make index 只更新数据，请先停止服务并执行 make upgrade。"
        )
    if not Path(ranking_source).is_dir():
        raise click.ClickException(
            f"未找到游戏榜单 CSV 目录：{ranking_source}；"
            "make index 需要同时构建游戏名录与游戏榜单。"
        )

    click.echo(f"读取游戏名录：{source}")
    click.echo(f"读取游戏榜单目录：{ranking_source}")

    try:
        stats = build_index(
            source, target, ranking_dir=ranking_source, strict_ranking=True
        )
    except IndexBuildError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        sync = refresh_all_flags(settings.database_path, stats.path, strict=True)
    except FlagSyncError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        f"已写入 {stats.path}：游戏名录 {stats.rows} 行 / {stats.consoles} 机种，"
        f"游戏榜单 {stats.ranking_rows} 条 / {stats.ranking_consoles} 机种，"
        f"耗时 {stats.seconds:.1f} 秒，文件 {stats.size / 1024 / 1024:.1f} MB。"
    )
    if sync is not None:
        click.echo(
            f"已同步标记：库存表 {sync.games_changed} 行，榜单 {sync.rankings_changed} 行。"
        )


if __name__ == "__main__":
    cli()
