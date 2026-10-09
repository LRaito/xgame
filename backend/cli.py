import click

from backend.config import get_settings
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


if __name__ == "__main__":
    cli()
