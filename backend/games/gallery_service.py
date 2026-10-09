from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, select

from backend.errors import NotFoundError, StorageError, ValidationError
from backend.games import paths
from backend.games.images import (
    SUPPORTED_IMAGE_LABEL,
    clean_image_description,
    detect_image_type,
    validate_image_size,
)
from backend.games.models import GALLERY_DESCRIPTION_MAX_LENGTH, Game, GameGalleryImage
from backend.storage.types import StorageBackend, StoredObjectStream

# 展示顺序用分数排序，与截图同一套：相邻名次之间留 _SCORE_STEP 的间隔，重排只改被
# 拖动那一行的分数（取相邻中值）；两分数挨到 _MIN_GAP 以内（浮点快被对半切没了）
# 就把整份按 _SCORE_STEP 重新铺开一遍——这就是「间隙不足时后台重排」。
_SCORE_STEP = 1000.0
_MIN_GAP = 1e-3


@dataclass(frozen=True)
class GalleryImageItem:
    id: int
    game_id: int
    sort_order: float
    description: str
    size: int
    created_at: datetime


class GalleryService:
    """游戏图集：一个游戏一套，**按游戏共享**（不记上传者，任何登录用户都能改）。

    与截图（ScreenshotService，按 (用户, 游戏) 隔离）相比只少了「用户」这一维：
    图片校验、分数排序、上传/删除流程都一致。字节落在游戏目录内的
    game/{类型}/{卡带ID}/image/ 下，所以换游戏类型时随目录一起迁移
    （见 GameService 的类型切换收尾）；删游戏时行与文件一并清掉。
    """

    def __init__(self, session: Session, storage: StorageBackend) -> None:
        self._session = session
        self._storage = storage

    def list_images(self, game_id: int) -> list[GalleryImageItem]:
        return [self._to_item(row) for row in self._ordered_rows(game_id)]

    def create_image(
        self,
        *,
        game_id: int,
        description: str,
        stream,
        size: int | None,
    ) -> GalleryImageItem:
        """一张图片入库：先校验内容、写盘，再落行；失败不留下孤儿文件。

        文件名与 content-type 都不作数：格式按内容 magic 判定，后缀也由此定下来。
        """
        game = self._session.get(Game, game_id)
        if game is None:
            raise NotFoundError("游戏不存在。")
        validate_image_size(size, label="图集")
        detected = detect_image_type(stream)
        if detected is None:
            raise ValidationError(f"只支持 {SUPPORTED_IMAGE_LABEL} 格式的图片。")
        extension, mime = detected
        description = self._clean_description(description)

        path = paths.gallery_file_path(
            game.game_type, game.cartridge_id, uuid.uuid4().hex, extension
        )
        # 落盘用「同目录临时文件 + 改名」，上传失败时磁盘上没有半截文件
        self._storage.upload(path, stream, size, mime)
        row = GameGalleryImage(
            game_id=game_id,
            sort_order=self._next_score(game_id),
            description=description,
            file_path=path,
            size=size,
            mime=mime,
        )
        self._session.add(row)
        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            self._delete_storage_key(path)
            raise
        self._session.refresh(row)
        return self._to_item(row)

    def update_description(
        self, image_id: int, description: str
    ) -> GalleryImageItem:
        row = self._get(image_id)
        row.description = self._clean_description(description)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return self._to_item(row)

    def move_image(self, image_id: int, to_index: int) -> list[GalleryImageItem]:
        """把这张拖到第 to_index 位（0 起，按拖动后的落点算），返回整份有序列表。

        只改这一行的分数：落在相邻两张之间取中值；间隔不够就先把整份重排铺开
        （间隙不足时的后台重排），再取中值。
        """
        row = self._get(image_id)
        rows = self._ordered_rows(row.game_id)
        index = next((i for i, item in enumerate(rows) if item.id == row.id), -1)
        if to_index < 0 or to_index >= len(rows):
            raise ValidationError("目标位置不合法。")
        if to_index == index:
            return [self._to_item(item) for item in rows]

        remaining = [item for item in rows if item.id != row.id]
        score = self._score_between(remaining, to_index)
        if score is None:
            # 间隙用尽：把其余行按步长重新铺开，再取中值（全表重排只发生在这一刻）
            for position, item in enumerate(remaining):
                item.sort_order = (position + 1) * _SCORE_STEP
                self._session.add(item)
            score = self._score_between(remaining, to_index)
        row.sort_order = score
        self._session.add(row)
        self._session.commit()
        return self.list_images(row.game_id)

    def delete_image(self, image_id: int) -> None:
        row = self._get(image_id)
        self._delete_storage_key(row.file_path)
        self._session.delete(row)
        self._session.commit()

    def open_image(self, image_id: int) -> tuple[StoredObjectStream, str]:
        """打开图集图片流，连同入库时定下的 mime；不存在 404。

        mime 由内容 magic 定（不是按后缀现猜），所以这里显式带出去当 content-type——
        例如 `.webp` 在部分 Python 的 `mimetypes` 表里还不认识，现猜会退成 octet-stream。
        """
        row = self._get(image_id)
        stream = self._storage.open_download(row.file_path)
        return stream, row.mime or stream.mime or "application/octet-stream"

    def _ordered_rows(self, game_id: int) -> list[GameGalleryImage]:
        return list(
            self._session.exec(
                select(GameGalleryImage)
                .where(GameGalleryImage.game_id == game_id)
                .order_by(col(GameGalleryImage.sort_order), col(GameGalleryImage.id))
            ).all()
        )

    def _next_score(self, game_id: int) -> float:
        """新图片排到末尾：最大分 + 一个步长。"""
        rows = self._ordered_rows(game_id)
        return rows[-1].sort_order + _SCORE_STEP if rows else _SCORE_STEP

    @staticmethod
    def _score_between(remaining: list[GameGalleryImage], to_index: int) -> float | None:
        """算出落在第 to_index 位该用的分数；相邻间隔已用尽时返回 None（该重排了）。"""
        previous = remaining[to_index - 1].sort_order if to_index > 0 else None
        following = (
            remaining[to_index].sort_order if to_index < len(remaining) else None
        )
        if previous is None and following is None:
            return _SCORE_STEP
        if previous is None:
            return following - _SCORE_STEP
        if following is None:
            return previous + _SCORE_STEP
        if following - previous <= _MIN_GAP:
            return None
        return (previous + following) / 2

    def _get(self, image_id: int) -> GameGalleryImage:
        row = self._session.get(GameGalleryImage, image_id)
        if row is None:
            raise NotFoundError("图集图片不存在。")
        return row

    @staticmethod
    def _clean_description(description: str | None) -> str:
        return clean_image_description(
            description, label="图集", max_length=GALLERY_DESCRIPTION_MAX_LENGTH
        )

    def _delete_storage_key(self, key: str | None) -> None:
        """删单个图片文件；失败只吞掉（多半是本来就不在了），不影响主流程。"""
        if not key:
            return
        try:
            self._storage.delete(key)
        except StorageError:
            pass

    @staticmethod
    def _to_item(row: GameGalleryImage) -> GalleryImageItem:
        return GalleryImageItem(
            id=row.id,
            game_id=row.game_id,
            sort_order=row.sort_order,
            description=row.description,
            size=row.size,
            created_at=row.created_at,
        )
