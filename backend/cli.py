from pathlib import Path

import click

from backend.config import RANKING_CSV_PATH, SEARCH_CSV_DIR, get_settings
from backend.database import ensure_data_dir, init_db, make_engine


@click.group()
def cli() -> None:
    """x 后端管理命令。"""


@cli.command("init-db")
def init_db_cmd() -> None:
    """创建数据库表。"""
    settings = get_settings()
    ensure_data_dir(settings)
    engine = make_engine(settings)
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
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--ranking-csv",
    type=click.Path(path_type=Path),
    default=None,
    help=f"游戏榜单 CSV（默认 {RANKING_CSV_PATH.name}）。",
)
@click.option("--skip-ranking", is_flag=True, help="只重建检索索引，不加载游戏榜单。")
def build_index_cmd(
    csv_dir: Path | None,
    out_path: Path | None,
    ranking_csv: Path | None,
    skip_ranking: bool,
) -> None:
    """构建游戏检索索引与游戏榜单（<数据根>/db/game.db）。可重复执行，直接覆盖旧文件。

    服务启动时发现索引不存在也会自动补建一次（见 search_index.ensure_game_index），
    榜单 CSV 变化时启动也会就地补一次；这个命令是手动重建/更新的入口：换了名录或榜单
    CSV、改了分词规则之后用它覆盖。
    """
    # import 放在函数里：cli 的其它命令不该为了这个可选功能多拖依赖
    from backend.games.search_index import IndexBuildError, build_index

    settings = get_settings()
    ensure_data_dir(settings)
    source = csv_dir or SEARCH_CSV_DIR
    target = out_path or settings.game_index_path
    ranking_source = None if skip_ranking else (ranking_csv or RANKING_CSV_PATH)

    click.echo(f"读取名录：{source}")
    if ranking_source is None:
        click.echo("跳过游戏榜单（--skip-ranking）。")
    elif Path(ranking_source).is_file():
        click.echo(f"读取榜单：{ranking_source}")
    else:
        click.echo(f"未找到榜单 CSV（{ranking_source}），本次只建检索索引。")

    try:
        stats = build_index(
            source, target, ranking_csv=ranking_source, strict_ranking=not skip_ranking
        )
    except IndexBuildError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        f"已写入 {stats.path}：{stats.rows} 行、{stats.consoles} 机种，"
        f"榜单 {stats.ranking_rows} 条 / {stats.ranking_consoles} 机种，"
        f"耗时 {stats.seconds:.1f} 秒，文件 {stats.size / 1024 / 1024:.1f} MB。"
    )


if __name__ == "__main__":
    cli()
