"""ドメイン層のリポジトリ契約。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from flow_res import Result

from app.contracts.messages.relationship import PersistedRelationshipSignal
from app.domain.aggregates.character_relationship import CharacterRelationship


class RepositoryErrorType(Enum):
    """リポジトリエラーの種別。"""

    NOT_FOUND = auto()
    UNEXPECTED = auto()
    VERSION_CONFLICT = auto()
    ALREADY_EXISTS = auto()


@dataclass
class RepositoryError(Exception):
    """リポジトリ層から返すエラー情報。"""

    type: RepositoryErrorType
    message: str


@dataclass(frozen=True, slots=True)
class ChatRecordReference:
    """Stable identity and owner of an already persisted chat row."""

    message_id: str
    user_id: str
    order_key: int
    is_new: bool = True


class IChatRecordRepository(ABC):
    """チャット正本の書き込み・重複確認契約。"""

    @abstractmethod
    async def add_message(
        self,
        *,
        character_id: str,
        user_id: str,
        channel: str,
        external_conversation_id: str,
        external_participant_id: str,
        external_message_id: str | None,
        role: str,
        message_content: Mapping[str, object],
        channel_metadata: Mapping[str, object],
    ) -> Result[ChatRecordReference, RepositoryError]:
        """チャンネルに依存しないチャットレコードを追加する。"""
        pass

    @abstractmethod
    async def find_by_external_message_id(
        self,
        *,
        channel: str,
        external_message_id: str,
    ) -> Result[ChatRecordReference | None, RepositoryError]:
        """外部メッセージIDから既存の正本IDを取得する。"""
        pass


class IMemoryConsolidatedChatSourceRepository(ABC):
    """memory生成へ取り込まれたchat行のprojection書き込み契約。"""

    @abstractmethod
    async def mark_consolidated(
        self,
        chat_ids: list[str],
        *,
        consolidated_at: datetime,
    ) -> Result[int, RepositoryError]:
        """指定chat IDをmemory処理済みとして記録する。"""

        pass


class ICharacterRelationshipRepository(ABC):
    """Persistence boundary for relationship state and signal evidence."""

    @abstractmethod
    async def record_provisional(
        self,
        signal: PersistedRelationshipSignal,
    ) -> Result[CharacterRelationship, RepositoryError]:
        """Idempotently record one immediate signal and recalculate affection."""

        pass

    @abstractmethod
    async def reconcile_confirmed(
        self,
        *,
        character_id: str,
        user_id: str,
        evaluated_chat_ids: list[str],
        signals: list[PersistedRelationshipSignal],
    ) -> Result[CharacterRelationship, RepositoryError]:
        """Replace overlapping provisional evidence with confirmed signals."""

        pass
