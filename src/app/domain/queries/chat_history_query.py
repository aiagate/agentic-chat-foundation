"""チャット履歴取得のクエリ契約。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from flow_res import Result

from app.contracts.messages.chat_history import ChatHistoryWindow
from app.contracts.messages.chat_type import ChatType

if TYPE_CHECKING:
    from app.domain.repositories.interfaces import RepositoryError


class IChatHistoryQuery(ABC):
    """チャット履歴を取得するクエリ契約。"""

    @abstractmethod
    async def get_recent_history(
        self,
        chat_type: ChatType,
        *,
        character_id: str,
        user_id: str,
        external_conversation_id: str,
        before_order_key: int | None = None,
        limit: int = 20,
    ) -> Result[ChatHistoryWindow, RepositoryError]:
        """指定したチャット種別の最新履歴を取得する。"""
        pass
