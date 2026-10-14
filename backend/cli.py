from pathlib import Path

import click

from backend.config import SEARCH_CSV_DIR, get_settings
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


@cli.command("index")
@click.option("--csv-dir", type=click.Path(path_type=Path), default=None)
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None)
def build_index_cmd(csv_dir: Path | None, out_path: Path | None) -> None:
    """构建游戏检索索引（<数据根>/db/game.db）。可重复执行，直接覆盖旧文件。

    服务启动时发现索引不存在也会自动补建一次（见 search_index.ensure_game_index），
    这个命令是手动重建/更新的入口：换了名录 CSV、改了分词规则之后用它覆盖。
    """
    # import 放在函数里：cli 的其它命令不该为了这个可选功能多拖依赖
    from backend.games.search_index import IndexBuildError, build_index

    settings = get_settings()
    ensure_data_dir(settings)
    source = csv_dir or SEARCH_CSV_DIR
    target = out_path or settings.game_index_path

    click.echo(f"读取名录：{source}")
    try:
        stats = build_index(source, target)
    except IndexBuildError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        f"已写入 {stats.path}：{stats.rows} 行、{stats.consoles} 机种，"
        f"耗时 {stats.seconds:.1f} 秒，文件 {stats.size / 1024 / 1024:.1f} MB。"
    )


if __name__ == "__main__":
    cli()
