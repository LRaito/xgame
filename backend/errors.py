class AppError(Exception):
    """领域错误，由 router 转成 JSON 4xx。"""


class AuthError(AppError):
    pass


class LoginLockedError(AppError):
    pass


class NotFoundError(AppError):
    pass


class StorageError(AppError):
    pass


class ValidationError(AppError):
    pass


class IndexUnavailableError(AppError):
    """游戏名录索引存在但打不开/读不了（坏库、版本过旧）。由 router 转成 503。"""


class DatabaseVersionError(Exception):
    """app.db 的结构版本与当前代码不匹配。

    只用于启动期与升级命令，不继承 ``AppError``：它不进入 HTTP 错误信封。
    """
