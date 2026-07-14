"""ドメイン層のリポジトリ契約。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from flow_res import Result


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


class IChatRecordRepository(ABC):
    """チャット正本の書き込み・重複確認契約。"""

    @abstractmethod
    async def add_message(
        self,
        *,
        channel: str,
        external_conversation_id: str,
        external_participant_id: str,
        external_message_id: str | None,
        role: str,
        message_content: Mapping[str, object],
        channel_metadata: Mapping[str, object],
    ) -> Result[str, RepositoryError]:
        """チャンネルに依存しないチャットレコードを追加する。"""
        pass

    @abstractmethod
    async def find_by_external_message_id(
        self,
        *,
        channel: str,
        external_message_id: str,
    ) -> Result[str | None, RepositoryError]:
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
