"""ULID ベース ID 値オブジェクトの基底。"""

from dataclasses import dataclass
from typing import TypeVar

from flow_res import Err, Ok, Result
from ulid import ULID

T = TypeVar("T", bound="BaseId")


@dataclass(frozen=True)
class BaseId:
    """ULID を包む不変 ID 値オブジェクトの基底。

    文字列表現と永続化変換を共通化し、各 ID 型の実装を薄く保つ。
    """

    _value: ULID

    @classmethod
    def generate(cls: type[T]) -> Result[T, Exception]:
        """新しい ID を生成する。

        Returns:
            生成した ID。
        """
        return Ok(cls(_value=ULID()))

    def to_primitive(self) -> str:
        """永続化向けの文字列に変換する。

        Returns:
            ULID の文字列表現。
        """
        return str(self._value)

    @classmethod
    def from_primitive(cls: type[T], value: str) -> Result[T, Exception]:
        """文字列から ID を復元する。

        Args:
            value: データベース由来の ULID 文字列。

        Returns:
            生成した ID。

        Raises:
            ValueError: 文字列が有効な ULID でない場合。
        """
        try:
            return Ok(cls(_value=ULID.from_str(value)))
        except ValueError as e:
            return Err(ValueError(f"Invalid ULID string: {value}", e))

    def __str__(self) -> str:
        """文字列表現を返す。"""
        return self.to_primitive()

    def __repr__(self) -> str:
        """開発者向け表現を返す。"""
        return f"{self.__class__.__name__}({self.to_primitive()})"
