from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, col, select

from backend.errors import NotFoundError, StorageError, ValidationError
from backend.games import paths
from backend.games.models import Game, GameCloudSnapshot, GameCloudSnapshotFile
from backend.games.sort_order import SCORE_STEP, score_between
from backend.storage.types import StorageBackend, StoredObjectStream

# 单个存档文件上限。Flash 的 .sol 很小，但 melonDS 的即时存档约 19–32MB，
# 所以按它抬高到 64MB；总请求上限仍由 nginx（512m）与 request_limit 兜住。
_SAVE_MAX_FILE_SIZE = 64 * 1024 * 1024
_SAVE_MAX_FILES = 64  # 一个快照最多容纳的文件数
_SAVE_REMARK_MAX = 100  # 描述上限字数
_SOL_MIME = "application/octet-stream"


def _clean_remark(remark: str | None) -> str:
    """去除首尾空白并校验长度，超长直接抛错而非静默截断。"""
    value = (remark or "").strip()
    if len(value) > _SAVE_REMARK_MAX:
        raise ValidationError(f"存档描述不能超过 {_SAVE_REMARK_MAX} 个字。")
    return value


@dataclass(frozen=True)
class CloudSnapshotItem:
    id: int
    game_id: int
    parent_id: int | None
    sort_order: float
    remark: str
    file_count: int
    total_size: int
    created_at: datetime


@dataclass(frozen=True)
class CloudSnapshotFile:
    id: int
    sort_order: int
    local_key: str
    name: str
    size: int


@dataclass(frozen=True)
class CloudSnapshotDetail:
    id: int
    game_id: int
    parent_id: int | None
    remark: str
    created_at: datetime
    files: list[CloudSnapshotFile] = field(default_factory=list)


@dataclass(frozen=True)
class SaveUpload:
    """一次“同步至云端”中的一个 .sol：写回浏览器所需的 key、展示名与字节流。"""

    local_key: str
    name: str
    stream: object
    size: int
    mime: str | None


class CloudSaveService:
    """云端存档：元数据在 SQLite，存档文件按整体快照落在 save/{用户名}/… 下。

    按 (user_id, game_id) 隔离；落盘路径带用户名，所以用户名在构造时传入。
    """

    def __init__(self, session: Session, storage: StorageBackend, username: str) -> None:
        self._session = session
        self._storage = storage
        self._username = username

    def list_snapshots(self, user_id: int, game_id: int) -> list[CloudSnapshotItem]:
        """按展示顺序（分数升序，越新越靠下）返回某游戏的全部快照。"""
        snapshots = self._ordered_rows(user_id, game_id)
        if not snapshots:
            return []
        ids = [snapshot.id for snapshot in snapshots]
        agg_rows = self._session.exec(
            select(
                GameCloudSnapshotFile.snapshot_id,
                func.count(GameCloudSnapshotFile.id),
                func.coalesce(func.sum(GameCloudSnapshotFile.size), 0),
            )
            .where(GameCloudSnapshotFile.snapshot_id.in_(ids))
            .group_by(GameCloudSnapshotFile.snapshot_id)
        ).all()
        agg = {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in agg_rows}
        return [
            CloudSnapshotItem(
                id=snapshot.id,
                game_id=snapshot.game_id,
                parent_id=snapshot.parent_id,
                sort_order=snapshot.sort_order,
                remark=snapshot.remark,
                file_count=agg.get(snapshot.id, (0, 0))[0],
                total_size=agg.get(snapshot.id, (0, 0))[1],
                created_at=snapshot.created_at,
            )
            for snapshot in snapshots
        ]

    def get_snapshot(self, user_id: int, snapshot_id: int) -> CloudSnapshotDetail:
        snapshot = self._get_owned_snapshot(user_id, snapshot_id)
        files = self._list_files(snapshot_id)
        return CloudSnapshotDetail(
            id=snapshot.id,
            game_id=snapshot.game_id,
            parent_id=snapshot.parent_id,
            remark=snapshot.remark,
            created_at=snapshot.created_at,
            files=files,
        )

    def create_snapshot(
        self,
        *,
        user_id: int,
        game_id: int,
        remark: str,
        uploads: list[SaveUpload],
    ) -> CloudSnapshotDetail:
        """uploads 逐文件写入后统一落库成一个整体快照。中途失败回滚已写的文件与行。"""
        if not uploads:
            raise ValidationError("没有可同步的存档文件。")
        if len(uploads) > _SAVE_MAX_FILES:
            raise ValidationError(f"存档文件数量过多（最多 {_SAVE_MAX_FILES} 个）。")
        cleaned: list[SaveUpload] = []
        for upload in uploads:
            if upload.size is None or upload.size <= 0:
                raise ValidationError("存档文件大小无效。")
            if upload.size > _SAVE_MAX_FILE_SIZE:
                raise ValidationError("存档文件过大。")
            local_key = (upload.local_key or "").strip()
            name = (upload.name or "").strip()
            if not local_key:
                raise ValidationError("存档文件缺少还原用的键。")
            cleaned.append(
                SaveUpload(
                    local_key=local_key,
                    name=name[:255] or f"save-{len(cleaned) + 1}",
                    stream=upload.stream,
                    size=upload.size,
                    mime=upload.mime,
                )
            )
        remark = _clean_remark(remark)

        game = self._session.get(Game, game_id)
        if game is None:
            raise NotFoundError("游戏不存在。")

        # 新快照自动接在同组最新一条后面；第一条没有父级。
        # 「最新」按创建时间定（与展示顺序无关，展示顺序可能被用户改过）。
        latest = self._session.exec(
            select(GameCloudSnapshot)
            .where(
                GameCloudSnapshot.user_id == user_id,
                GameCloudSnapshot.game_id == game_id,
            )
            .order_by(
                col(GameCloudSnapshot.created_at).desc(),
                col(GameCloudSnapshot.id).desc(),
            )
            .limit(1)
        ).first()
        snapshot = GameCloudSnapshot(
            user_id=user_id,
            game_id=game_id,
            remark=remark,
            parent_id=latest.id if latest is not None else None,
            # 追加到末尾：越新的存档越靠下
            sort_order=self._next_score(user_id, game_id),
        )
        self._session.add(snapshot)
        self._session.flush()  # 先拿 snapshot.id 给存档行做外键

        written: list[str] = []
        file_rows: list[GameCloudSnapshotFile] = []
        try:
            for index, upload in enumerate(cleaned):
                path = paths.save_file_path(
                    self._username, game.game_type, game.cartridge_id, uuid.uuid4().hex
                )
                self._storage.upload(path, upload.stream, upload.size, upload.mime or _SOL_MIME)
                written.append(path)
                file_rows.append(
                    GameCloudSnapshotFile(
                        snapshot_id=snapshot.id,
                        sort_order=index,
                        local_key=upload.local_key,
                        name=upload.name,
                        size=upload.size,
                        mime=upload.mime or _SOL_MIME,
                        file_path=path,
                    )
                )
            for row in file_rows:
                self._session.add(row)
            self._session.commit()
        except Exception:
            # 写文件/落库中途失败：撤掉未提交的行，并尽力删已写的文件，避免孤儿文件
            self._session.rollback()
            for path in written:
                self._delete_storage_key(path)
            raise
        self._session.refresh(snapshot)
        return CloudSnapshotDetail(
            id=snapshot.id,
            game_id=snapshot.game_id,
            parent_id=snapshot.parent_id,
            remark=snapshot.remark,
            created_at=snapshot.created_at,
            files=self._to_file_list(file_rows),
        )

    def delete_snapshot(self, user_id: int, snapshot_id: int) -> None:
        snapshot = self._get_owned_snapshot(user_id, snapshot_id)
        # 子节点不级联删除，也不接续祖父：直接变成顶层存档。
        children = self._session.exec(
            select(GameCloudSnapshot).where(
                GameCloudSnapshot.parent_id == snapshot_id
            )
        ).all()
        for child in children:
            child.parent_id = None
            self._session.add(child)
        file_rows = self._session.exec(
            select(GameCloudSnapshotFile).where(
                GameCloudSnapshotFile.snapshot_id == snapshot_id
            )
        ).all()
        for row in file_rows:
            self._delete_storage_key(row.file_path)
            self._session.delete(row)
        self._session.delete(snapshot)
        self._session.commit()

    def set_parent(
        self, user_id: int, snapshot_id: int, parent_id: int | None
    ) -> CloudSnapshotDetail:
        """设置或清除快照的父级；parent_id=None 表示设为顶层。"""
        child = self._get_owned_snapshot(user_id, snapshot_id)
        if parent_id is not None:
            if parent_id == snapshot_id:
                raise ValidationError("不能把存档挂到自己下面。")
            parent = self._get_owned_snapshot(user_id, parent_id)
            if parent.game_id != child.game_id:
                raise ValidationError("只能在同一游戏的存档之间建立层级。")
            self._assert_no_cycle(child, parent)
        if child.parent_id != parent_id:
            child.parent_id = parent_id
            self._session.add(child)
            self._session.commit()
        return self.get_snapshot(user_id, snapshot_id)

    def move_snapshot(
        self, user_id: int, snapshot_id: int, to_index: int
    ) -> list[CloudSnapshotItem]:
        """把快照在同级兄弟里挪到第 to_index 位（0 起），返回整份有序列表。

        同级 = 同一个 parent_id 的那一段（None 自成一档，即全部顶层）。只改被移动
        那一行的分数；相邻间隔用尽时先把同 (user, game) 的整份按当前顺序重铺一遍。
        """
        snapshot = self._get_owned_snapshot(user_id, snapshot_id)
        rows = self._ordered_rows(user_id, snapshot.game_id)
        siblings = [row for row in rows if row.parent_id == snapshot.parent_id]
        index = next((i for i, row in enumerate(siblings) if row.id == snapshot.id), -1)
        if to_index < 0 or to_index >= len(siblings):
            raise ValidationError("目标位置不合法。")
        if to_index == index:
            return self.list_snapshots(user_id, snapshot.game_id)

        remaining = [row for row in siblings if row.id != snapshot.id]
        score = score_between(remaining, to_index)
        if score is None:
            # 间隙用尽：把整份按当前顺序重新铺开，再取中值（全表重排只发生在这一刻）
            for position, row in enumerate(rows):
                row.sort_order = (position + 1) * SCORE_STEP
                self._session.add(row)
            score = score_between(remaining, to_index)
        snapshot.sort_order = score
        self._session.add(snapshot)
        self._session.commit()
        return self.list_snapshots(user_id, snapshot.game_id)

    def _assert_no_cycle(self, child: GameCloudSnapshot, parent: GameCloudSnapshot) -> None:
        """沿父链向上走：遇到 child 就说明会成环；父链本身异常（重复/跨账号）也拦下。"""
        seen: set[int] = set()
        cursor: GameCloudSnapshot | None = parent
        while cursor is not None:
            if cursor.id == child.id:
                raise ValidationError("不能形成循环的存档层级。")
            if cursor.id in seen:
                raise ValidationError("存档层级数据异常。")
            if cursor.user_id != child.user_id or cursor.game_id != child.game_id:
                raise ValidationError("存档层级数据异常。")
            seen.add(cursor.id)
            cursor = (
                self._session.get(GameCloudSnapshot, cursor.parent_id)
                if cursor.parent_id is not None
                else None
            )

    def update_remark(self, user_id: int, snapshot_id: int, remark: str) -> CloudSnapshotDetail:
        snapshot = self._get_owned_snapshot(user_id, snapshot_id)
        snapshot.remark = _clean_remark(remark)
        self._session.add(snapshot)
        self._session.commit()
        self._session.refresh(snapshot)
        return CloudSnapshotDetail(
            id=snapshot.id,
            game_id=snapshot.game_id,
            parent_id=snapshot.parent_id,
            remark=snapshot.remark,
            created_at=snapshot.created_at,
            files=self._list_files(snapshot.id),
        )

    def open_file(
        self, user_id: int, snapshot_id: int, file_id: int
    ) -> tuple[StoredObjectStream, str]:
        snapshot = self._get_owned_snapshot(user_id, snapshot_id)
        row = self._session.get(GameCloudSnapshotFile, file_id)
        if row is None or row.snapshot_id != snapshot.id:
            raise NotFoundError("存档文件不存在。")
        stream = self._storage.open_download(row.file_path)
        return stream, _save_download_filename(row.name)

    def _get_owned_snapshot(self, user_id: int, snapshot_id: int) -> GameCloudSnapshot:
        snapshot = self._session.get(GameCloudSnapshot, snapshot_id)
        if snapshot is None or snapshot.user_id != user_id:
            # 不区分“不存在”与“别人的”，避免越权探测
            raise NotFoundError("云端存档不存在。")
        return snapshot

    def _ordered_rows(self, user_id: int, game_id: int) -> list[GameCloudSnapshot]:
        return list(
            self._session.exec(
                select(GameCloudSnapshot)
                .where(
                    GameCloudSnapshot.user_id == user_id,
                    GameCloudSnapshot.game_id == game_id,
                )
                .order_by(
                    col(GameCloudSnapshot.sort_order),
                    col(GameCloudSnapshot.id),
                )
            ).all()
        )

    def _next_score(self, user_id: int, game_id: int) -> float:
        """新快照追加到末尾：最大分 + 一个步长（空列表从步长起算）。"""
        rows = self._ordered_rows(user_id, game_id)
        return rows[-1].sort_order + SCORE_STEP if rows else SCORE_STEP

    def _list_files(self, snapshot_id: int) -> list[CloudSnapshotFile]:
        rows = self._session.exec(
            select(GameCloudSnapshotFile)
            .where(GameCloudSnapshotFile.snapshot_id == snapshot_id)
            .order_by(col(GameCloudSnapshotFile.sort_order))
        ).all()
        return self._to_file_list(rows)

    def _delete_storage_key(self, key: str | None) -> None:
        """删单个存档文件；失败只吞掉，不影响主流程。"""
        if not key:
            return
        try:
            self._storage.delete(key)
        except StorageError:
            pass

    @staticmethod
    def _to_file_list(rows) -> list[CloudSnapshotFile]:
        return [
            CloudSnapshotFile(
                id=row.id,
                sort_order=row.sort_order,
                local_key=row.local_key,
                name=row.name,
                size=row.size,
            )
            for row in rows
        ]


def _save_download_filename(name: str) -> str:
    """对外下载文件名：name 已带扩展名（如 EmulatorJS 的 .state）则原样返回，
    否则按 Flash 旧约定补 .sol（Flash 的本地键不含扩展名）。"""
    name = (name or "").strip()
    if not name:
        return "存档"
    # 以一个点视为“已含扩展名”，Flash 历史 name 均不带点，行为不变
    if "." in name:
        return name
    return f"{name}.sol"
