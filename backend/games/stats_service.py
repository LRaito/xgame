from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from backend.errors import NotFoundError, ValidationError
from backend.games.models import (
    PROGRESS_COMPLETED,
    PROGRESS_IN_PROGRESS,
    PROGRESS_NOT_STARTED,
    Game,
    GameUserStat,
)

GAME_PROGRESS = (PROGRESS_NOT_STARTED, PROGRESS_IN_PROGRESS, PROGRESS_COMPLETED)

_PROGRESS_LABELS = {
    PROGRESS_NOT_STARTED: "未开始",
    PROGRESS_IN_PROGRESS: "进行中",
    PROGRESS_COMPLETED: "已通关",
}

# 单次上报的秒数上限：前端每 30 秒发一次心跳，5 分钟足够覆盖一次 sleep/卡顿，
# 再多就当成时钟跳变或刷量丢掉。
PLAYTIME_ADD_MAX = 300
# 手动设置总时长的上限（小时），约 11 年
PLAYTIME_SET_MAX_HOURS = 100000

_SECONDS_PER_HOUR = 3600


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class GameStat:
    play_seconds: int
    progress: str


class GameStatsService:
    """游玩统计按(用户, 游戏)一行：累计时长 + 进度，两者都存 SQLite。

    刻意与游戏类型无关——Flash / H5 / 主机 ROM 走的是同一条上报路径。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def map_for_games(self, user_id: int, game_ids: list[int]) -> dict[int, GameStat]:
        """一次查询拿一批游戏的统计，避免列表接口逐个查。"""
        ids = [gid for gid in {int(g) for g in game_ids} if gid > 0]
        if not ids:
            return {}
        rows = self._session.exec(
            select(GameUserStat).where(
                GameUserStat.user_id == user_id,
                col(GameUserStat.game_id).in_(ids),
            )
        ).all()
        return {
            row.game_id: GameStat(play_seconds=row.play_seconds, progress=row.progress)
            for row in rows
        }

    def add_playtime(self, user_id: int, game_id: int, seconds: int) -> int:
        """累加一段游玩时长，返回累加后的总秒数。

        seconds 越界在这里收敛而不是靠 Query 校验：参数校验失败走 422 会绕开
        统一错误信封（同 GameService.list_recent 的处理思路）。
        """
        self._require_game(game_id)
        # 用 round 而不是截断：前端本来就按毫秒取整后再上报，这里再截一刀
        # 会让每次心跳都少零点几秒。收敛到 0..MAX 是防时钟跳变与刷量。
        step = max(0, min(round(float(seconds or 0)), PLAYTIME_ADD_MAX))
        if step == 0:
            row = self._find(user_id, game_id)
            return 0 if row is None else row.play_seconds

        def _bump(row: GameUserStat) -> None:
            row.play_seconds += step

        return self._mutate(user_id, game_id, _bump).play_seconds

    def set_playtime(self, user_id: int, game_id: int, hours: float) -> int:
        """把总时长直接改写成指定小时数（之后继续游玩仍在此基础上累加）。"""
        self._require_game(game_id)
        try:
            value = float(hours)
        except (TypeError, ValueError):
            raise ValidationError("总时长必须是一个数字。") from None
        if value != value or value in (float("inf"), float("-inf")):
            raise ValidationError("总时长必须是一个数字。")
        if value < 0 or value > PLAYTIME_SET_MAX_HOURS:
            raise ValidationError(f"总时长需在 0 到 {PLAYTIME_SET_MAX_HOURS} 小时之间。")
        seconds = round(value * _SECONDS_PER_HOUR)
        return self._mutate(
            user_id, game_id, lambda row: setattr(row, "play_seconds", seconds)
        ).play_seconds

    def set_progress(self, user_id: int, game_id: int, progress: str) -> str:
        """设置进度；只认未开始 / 进行中 / 已通关三种。"""
        self._require_game(game_id)
        value = (progress or "").strip()
        if value not in GAME_PROGRESS:
            labels = "、".join(_PROGRESS_LABELS[item] for item in GAME_PROGRESS)
            raise ValidationError(f"游戏进度只能是：{labels}。")
        self._mutate(user_id, game_id, lambda row: setattr(row, "progress", value))
        return value

    def _require_game(self, game_id: int) -> None:
        row = self._session.get(Game, game_id)
        if row is None or not row.game_path:
            raise NotFoundError("游戏不存在。")

    def _find(self, user_id: int, game_id: int) -> GameUserStat | None:
        return self._session.exec(
            select(GameUserStat).where(
                GameUserStat.user_id == user_id,
                GameUserStat.game_id == game_id,
            )
        ).first()

    def _mutate(self, user_id: int, game_id: int, apply) -> GameUserStat:
        """取行、让 apply 就地改字段、落库；没有行则新建。

        apply 必须**就地修改** row（不要写成返回新值的表达式，那样改不到对象上）。
        并发首写撞唯一约束时回滚重来一次。
        """
        try:
            row = self._write(user_id, game_id, apply)
        except IntegrityError:
            self._session.rollback()
            row = self._write(user_id, game_id, apply)
        return row

    def _write(self, user_id: int, game_id: int, apply) -> GameUserStat:
        row = self._find(user_id, game_id)
        if row is None:
            row = GameUserStat(user_id=user_id, game_id=game_id)
        apply(row)
        row.updated_at = _utcnow()
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row
