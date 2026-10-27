"""展示顺序的分数排序原语（截图 / 图集 / 云端存档共用的那套算法）。

分数越小越靠前。新行追加到末尾（最大分 + 步长），移动只改被移动那一行的分数
（取相邻两分数的中值）；相邻间隔已经用尽时返回 ``None``，由调用方把整份按
``(position + 1) * SCORE_STEP`` 重铺一遍再算。
"""

from typing import Protocol

SCORE_STEP = 1000.0
MIN_GAP = 1e-3


class _Scored(Protocol):
    sort_order: float


def score_between(remaining: list[_Scored], to_index: int) -> float | None:
    """算出落在第 ``to_index`` 位该用的分数；相邻间隔已用尽时返回 None。

    ``remaining`` 是**已经移走目标行**之后的有序列表。
    """
    previous = remaining[to_index - 1].sort_order if to_index > 0 else None
    following = remaining[to_index].sort_order if to_index < len(remaining) else None
    if previous is None and following is None:
        return SCORE_STEP
    if previous is None:
        return following - SCORE_STEP
    if following is None:
        return previous + SCORE_STEP
    if following - previous <= MIN_GAP:
        return None
    return (previous + following) / 2
