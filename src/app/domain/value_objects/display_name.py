"""表示名の値オブジェクト。"""

from dataclasses import dataclass

from flow_res import Err, Ok, Result


@dataclass(frozen=True)
class DisplayName:
    """表示名を表す不変値オブジェクト。

    長さと空白の制約を持ち、表示や永続化で同じ値を使う。
    """

    _value: str

    # ディスプレイネームの最小・最大文字数
    MIN_LENGTH: int = 1
    MAX_LENGTH: int = 100

    def to_primitive(self) -> str:
        """永続化向けの文字列に変換する。

        Returns:
            表示名の文字列表現。
        """
        return self._value

    @classmethod
    def from_primitive(cls, value: str) -> Result["DisplayName", Exception]:
        """文字列から表示名を復元する。

        Args:
            value: データベース由来の表示名。

        Returns:
            生成した表示名。

        Raises:
            ValueError: 表示名として不正な場合。
        """
        if not value:
            return Err(ValueError("Display name cannot be empty."))
        if len(value) < cls.MIN_LENGTH:
            return Err(
                ValueError(
                    f"Display name must be at least {cls.MIN_LENGTH} characters long."
                )
            )
        if len(value) > cls.MAX_LENGTH:
            return Err(
                ValueError(f"Display name must not exceed {cls.MAX_LENGTH} characters.")
            )
        if value != value.strip():
            return Err(
                ValueError("Display name cannot have leading or trailing whitespace.")
            )
        return Ok(cls(_value=value))

    def __str__(self) -> str:
        """文字列表現を返す。"""
        return self.to_primitive()

    def __repr__(self) -> str:
        """開発者向け表現を返す。"""
        return f"DisplayName({self.to_primitive()})"
