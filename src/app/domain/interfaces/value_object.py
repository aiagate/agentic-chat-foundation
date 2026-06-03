"""プリミティブ型と相互変換できる値オブジェクトの契約。"""

from typing import Protocol, TypeVar, runtime_checkable

from flow_res import Result

T = TypeVar("T")


@runtime_checkable
class IValueObject(Protocol[T]):
    """プリミティブ型と相互変換できる値オブジェクトの契約。

    この契約を満たす型は、永続化層との受け渡しで共通処理を使える。

    Type Parameters:
        T: 永続化に使うプリミティブ型。
    """

    def to_primitive(self) -> T:
        """永続化向けのプリミティブ値に変換する。

        Returns:
            データベース保存に使えるプリミティブ値。
        """
        ...

    @classmethod
    def from_primitive(cls, value: T) -> Result["IValueObject[T]", Exception]:
        """プリミティブ値から値オブジェクトを復元する。

        Args:
            value: データベースから取得したプリミティブ値。

        Returns:
            成功時は生成したインスタンス、失敗時は検証エラー。
        """
        ...
