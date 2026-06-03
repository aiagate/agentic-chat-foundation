"""チャット履歴取得のクエリ契約。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from flow_res import Result

from app.contracts.messages.chat_history import ChatHistoryItem
from app.domain.value_objects.chat_type import ChatType

if TYPE_CHECKING:
    from app.domain.repositories.interfaces import RepositoryError


class IChatHistoryQuery(ABC):
    """チャット履歴を取得するクエリ契約。"""

    @abstractmethod
    async def get_recent_history(
        self,
        chat_type: ChatType,
        user_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        limit: int = 20,
    ) -> Result[list[ChatHistoryItem], RepositoryError]:
        """指定したチャット種別の最新履歴を取得する。"""
        pass
