"""ドメイン層のリポジトリ契約。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from flow_res import Result

from app.domain.aggregates.chat import Chat


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


class IRepository[T](ABC):
    """追加・更新・削除を扱うリポジトリ契約。

    ID 参照を前提にしない集約で使う。

    Type Parameters:
        T: エンティティ型。
    """

    @abstractmethod
    async def add(self, entity: T) -> Result[T, RepositoryError]:
        """新しいエンティティを追加する。"""
        pass

    @abstractmethod
    async def update(self, entity: T) -> Result[T, RepositoryError]:
        """既存エンティティを更新する。"""
        pass

    @abstractmethod
    async def delete(self, entity: T) -> Result[None, RepositoryError]:
        """エンティティを削除する。"""
        pass


class IRepositoryWithId[T, K](IRepository[T], ABC):
    """ID 参照を追加したリポジトリ契約。

    Type Parameters:
        T: エンティティ型。
        K: 主キー型。
    """

    @abstractmethod
    async def get_by_id(self, id: K) -> Result[T, RepositoryError]:
        """ID でエンティティを取得する。"""
        pass


class IChatRecordRepository(ABC):
    """チャット正本の書き込み契約。"""

    @abstractmethod
    async def add(
        self,
        chat: Chat,
        *,
        user_id: str,
        role: str,
    ) -> Result[Chat, RepositoryError]:
        """チャットレコードを追加する。"""
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
