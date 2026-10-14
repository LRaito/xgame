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
    """游戏检索索引存在但打不开/读不了（坏库、版本过旧）。由 router 转成 503。"""
