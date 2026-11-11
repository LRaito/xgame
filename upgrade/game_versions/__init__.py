"""game.db 结构迁移版本注册表。

只登记结构迁移；游戏名录数据与游戏榜单数据仍由 `make index` 全量构建。
"""

from upgrade.game_versions import v7

VERSION_MODULES = (v7,)

MIGRATIONS = {module.VERSION: module.migrate for module in VERSION_MODULES}
