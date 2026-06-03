"""監査時刻を持つドメイン型の契約。"""

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class IAuditable(Protocol):
    """作成時刻と更新時刻を持つ型の契約。

    リポジトリ層が `created_at` と `updated_at` を管理する前提で使う。
    """

    created_at: datetime
    updated_at: datetime
