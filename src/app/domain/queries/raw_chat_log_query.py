"""長期記憶整理用の生ログ取得クエリ契約。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from flow_res import Result

from app.contracts.messages.chat_type import ChatType

if TYPE_CHECKING:
    from app.domain.repositories.interfaces import RepositoryError


@dataclass(frozen=True, slots=True)
class LongTermMemorySourceItem:
    """意味圧縮の入力になる生ログ1件。"""

    id: str
    user_id: str
    role: str
    chat_type: ChatType
    message_content: dict[str, Any]
    created_at: datetime | None
    character_id: str


class IRawChatLogQuery(ABC):
    """長期記憶整理向けの生ログ取得契約。"""

    @abstractmethod
    async def list_pending_memory_user_ids(
        self,
        character_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 1000,
    ) -> Result[list[str], RepositoryError]:
        """対象ログを持つユーザーIDの一覧を取得する。"""
        pass

    @abstractmethod
    async def get_pending_memory_source_items(
        self,
        character_id: str,
        user_id: str,
        chat_type: ChatType,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 1000,
    ) -> Result[list[LongTermMemorySourceItem], RepositoryError]:
        """指定ユーザーと時間範囲の生ログを取得する。"""
        pass
