"""楽観ロック用のバージョンを持つ型の契約。"""

from typing import Protocol, runtime_checkable

from app.domain.value_objects import Version


@runtime_checkable
class IVersionable(Protocol):
    """`version` フィールドを持つ型の契約。

    リポジトリ層が更新時に楽観ロックの判定に使う。
    """

    version: Version
