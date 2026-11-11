"""数据库结构升级版本注册表。

只在这里登记版本模块；顺序由 ``VERSION`` 决定，必须从 1 连续递增。
是否执行某个版本完全由 ``system_config.db_version`` 决定，不靠幂等代码。
"""

from upgrade.versions import v1

VERSION_MODULES = (v1,)

MIGRATIONS = {module.VERSION: module.upgrade for module in VERSION_MODULES}
