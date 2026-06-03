"""楽観ロック用バージョンの値オブジェクト。"""

from __future__ import annotations

from dataclasses import dataclass

from flow_res import Err, Ok, Result


@dataclass(frozen=True)
class Version:
    """更新競合を検出するためのバージョン値。

    単純な整数を包み、永続化や比較の意味を明示する。
    """

    _value: int

    def to_primitive(self) -> int:
        """永続化向けの整数に変換する。"""
        return self._value

    @classmethod
    def from_primitive(cls, value: int) -> Result[Version, Exception]:
        """整数からバージョンを復元する。

        Args:
            value: 非負のバージョン番号。

        Returns:
            生成した Version か検証エラー。
        """
        if not isinstance(value, int):  # type: ignore[reportUnnecessaryIsInstance]
            return Err(TypeError(f"Version must be int, got {type(value).__name__}"))
        if value < 0:
            return Err(ValueError("Version must be non-negative"))
        return Ok(cls(_value=value))

    def increment(self) -> Version:
        """1 つ進めた新しいバージョンを返す。

        Returns:
            インクリメント後の Version。
        """
        return Version(_value=self._value + 1)

    def __str__(self) -> str:
        return str(self._value)

    def __repr__(self) -> str:
        return f"Version({self._value})"
