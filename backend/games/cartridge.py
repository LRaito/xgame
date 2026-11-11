"""卡带 ID 的比对归一。

只做「去首尾空白 + 转大写」，不校验、不抛异常。落库前的校验仍在
`backend.games.service.validate_cartridge_id()`；榜单 CSV 与映射表必须能安全处理
空格、小写、甚至根本不是合法卡带 ID 的文本，所以这里不能用会抛错的版本。
"""


def normalize_cartridge_id(raw: str) -> str:
    return (raw or "").strip().upper()
