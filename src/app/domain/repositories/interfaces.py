"""ドメイン層のリポジトリ契約。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, overload

from flow_res import Result

from app.domain.queries.chat_history_query import IChatHistoryQuery
from app.domain.queries.raw_chat_log_query import IRawChatLogQuery


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


class IUnitOfWork(ABC):
    """トランザクション境界を表す Unit of Work 契約。"""

    @overload
    def GetRepository[T](self, entity_type: type[T]) -> IRepository[T]:
        """追加・更新・削除用のリポジトリを取得する。

        Args:
            entity_type: ドメインエンティティ型。

        Returns:
            リポジトリ実装。
        """
        ...

    @overload
    def GetRepository[T, K](
        self, entity_type: type[T], key_type: type[K]
    ) -> IRepositoryWithId[T, K]:
        """ID 参照付きリポジトリを取得する。

        Args:
            entity_type: ドメインエンティティ型。
            key_type: 主キー型。

        Returns:
            ID 参照を含むリポジトリ実装。
        """
        ...

    @abstractmethod
    def GetRepository[T, K](
        self, entity_type: type[T], key_type: type[K] | None = None
    ) -> IRepository[T] | IRepositoryWithId[T, K]:
        """エンティティ型に対応するリポジトリを取得する。

        Args:
            entity_type: ドメインエンティティ型。
            key_type: 任意の主キー型。

        Returns:
            リポジトリ実装。
        """
        pass

    @abstractmethod
    async def commit(self) -> Result[None, RepositoryError]:
        """トランザクションを確定する。"""
        pass

    @abstractmethod
    async def rollback(self) -> None:
        """トランザクションを破棄して巻き戻す。"""
        pass

    @abstractmethod
    def GetChatHistoryQuery(self) -> IChatHistoryQuery:
        """チャット履歴クエリを取得する。"""
        pass

    @abstractmethod
    def GetRawChatLogQuery(self) -> IRawChatLogQuery:
        """生ログクエリを取得する。"""
        pass

    @abstractmethod
    async def __aenter__(self) -> IUnitOfWork:
        """非同期コンテキストに入る。"""
        pass

    @abstractmethod
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """非同期コンテキストを抜ける。"""
        pass
