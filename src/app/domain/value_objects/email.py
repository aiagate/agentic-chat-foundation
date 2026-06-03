"""メールアドレスの値オブジェクト。"""

import re
from dataclasses import dataclass
from typing import ClassVar

from flow_res import Err, Ok, Result


@dataclass(frozen=True)
class Email:
    """メールアドレスを表す不変値オブジェクト。

    余分な空白を除去し、簡易形式チェックを通した値だけを保持する。
    """

    _value: str

    # RFC 5322準拠の簡易的な正規表現パターン
    # - ローカル部: 英数字、ドット、アンダースコア、パーセント、プラス、ハイフン
    # - ドメイン部: 英数字とハイフン、最後はドット + 2文字以上のTLD
    EMAIL_REGEX: ClassVar[re.Pattern[str]] = re.compile(
        r"^[a-zA-Z0-9_%+-]+(?:\.[a-zA-Z0-9_%+-]+)*@"
        r"[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$"
    )

    def to_primitive(self) -> str:
        """永続化向けの文字列に変換する。

        Returns:
            メールアドレスの文字列表現。
        """
        return self._value

    @classmethod
    def from_primitive(cls, value: str) -> Result["Email", Exception]:
        """文字列からメールアドレスを復元する。

        Args:
            value: データベース由来のメールアドレス。

        Returns:
            生成したメールアドレス。

        Raises:
            ValueError: 形式が不正な場合。
        """
        if not value:
            return Err(ValueError("Email cannot be empty."))
        normalized = value.strip()
        if not normalized:
            return Err(ValueError("Email cannot be empty."))
        if not cls.EMAIL_REGEX.match(normalized):
            return Err(ValueError(f"Invalid email format: {normalized}"))
        return Ok(cls(_value=normalized))

    def __str__(self) -> str:
        """文字列表現を返す。"""
        return self.to_primitive()

    def __repr__(self) -> str:
        """開発者向け表現を返す。"""
        return f"Email({self.to_primitive()})"
