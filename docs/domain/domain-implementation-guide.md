# Domain層実装ガイド

最終更新日: 2026-06-03

このドキュメントは、Domain層（ドメイン層）の実装方法と、プロジェクトで使用するパターンを説明します。

このリポジトリでは、アプリケーション境界の契約は `src/app/contracts/ports/` と `src/app/contracts/messages/` に集約しています。
`src/app/domain/interfaces/` は、Domain層の中で再利用する契約だけを置く場所です。

---

## 目次

1. [Domain層の役割](#domain層の役割)
2. [ディレクトリ構成](#ディレクトリ構成)
3. [Aggregate（集約）の実装](#aggregate集約の実装)
4. [インターフェースと契約の配置](#インターフェースと契約の配置)
5. [バリデーション](#バリデーション)
6. [タイムスタンプ管理（IAuditable）](#タイムスタンプ管理iauditable)
7. [ベストプラクティス](#ベストプラクティス)
8. [アンチパターン](#アンチパターン)

---

## Domain層の役割

Domain層は**ビジネスロジックの中核**であり、以下の責務を持ちます：

- [OK] **ビジネスルールの定義**: ドメインの不変条件（Invariants）を保証
- [OK] **エンティティと集約の管理**: ドメインオブジェクトのライフサイクル管理
- [OK] **フレームワーク非依存**: 純粋なPythonオブジェクトとして実装
- [NG] **データベースアクセスは行わない**: インフラストラクチャ層の責務
- [NG] **外部APIを呼び出さない**: インフラストラクチャ層の責務
- [NG] **UIロジックを持たない**: プレゼンテーション層の責務

---

## ディレクトリ構成

```
src/app/domain/
├── aggregates/          # 集約ルート
│   ├── chat.py
│   ├── team.py
│   ├── team_membership.py
│   └── user.py
├── interfaces/          # Domain内部で再利用する契約
│   ├── auditable.py
│   ├── value_object.py
│   └── versionable.py
├── queries/             # 読み取り専用クエリ契約
├── repositories/        # リポジトリ / Unit of Work 契約
└── value_objects/       # 値オブジェクト
    ├── display_name.py
    ├── email.py
    ├── user_id.py
    └── version.py
```

### ファイル命名規則

- **集約**: `snake_case.py`（例: `user.py`, `team_membership.py`）
- **クラス名**: `PascalCase`（例: `User`, `TeamMembership`）
- **インターフェース**: `I` プレフィックス（例: `IAuditable`）

---

## Aggregate（集約）の実装

### 現行の実装スタイル

このリポジトリの集約は、`@dataclass(kw_only=True, slots=True)` を基本にしています。
代表例は `src/app/domain/aggregates/user.py`、`src/app/domain/aggregates/team.py`、`src/app/domain/aggregates/chat.py`、`src/app/domain/aggregates/team_membership.py` です。

```python
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.value_objects import DisplayName, Email, UserId, Version


@dataclass(kw_only=True, slots=True)
class User:
    _id: UserId = field(
        init=False,
        default_factory=lambda: UserId.generate().expect("UserId.generate should succeed"),
    )
    _display_name: DisplayName
    _email: Email
    _version: Version = field(init=False, default_factory=lambda: Version(0))
    _created_at: datetime = field(init=False, default_factory=lambda: datetime.now(UTC))
    _updated_at: datetime = field(init=False, default_factory=lambda: datetime.now(UTC))

    @classmethod
    def register(cls, display_name: DisplayName, email: Email) -> "User":
        return cls(_display_name=display_name, _email=email)

    def change_email(self, new_email: Email) -> "User":
        self._email = new_email
        return self
```

### 実装原則

- 集約の状態は、ドメインメソッドから変更する
- 集約外の参照は ID または値オブジェクトで持つ
- `version`、`created_at`、`updated_at` は集約に持たせるが、更新責任はインフラ層に寄せる
- 検証は `__post_init__` か、生成用クラスメソッドの内部で行う

`TeamMembership` のような状態遷移を持つ集約では、`join()`、`request_join()`、`activate()`、`leave()` のようなビジネス名を使います。

---

## インターフェースと契約の配置

このリポジトリでは、契約の種類ごとに置き場所を分けています。

### `src/app/domain/interfaces/`

Domain内部で再利用する契約を置きます。

- `auditable.py`: `IAuditable`
- `value_object.py`: `IValueObject`
- `versionable.py`: `IVersionable`

`IValueObject` は `src/app/infrastructure/orm_mapping.py` の変換処理で使います。
`IAuditable` と `IVersionable` は `src/app/infrastructure/repositories/generic_repository.py` の更新処理で使います。

### `src/app/domain/repositories/`

リポジトリと Unit of Work の契約を置きます。

- `IRepository`
- `IRepositoryWithId`
- `IUnitOfWork`
- `RepositoryError`
- `RepositoryErrorType`

### `src/app/domain/queries/`

読み取り専用のクエリ契約を置きます。

- `IChatHistoryQuery`
- `IRawChatLogQuery`

### `src/app/contracts/ports/`

アプリケーション境界の port を置きます。

- `IAgentProfileService`
- `IAIService`
- `IEventBus`
- `IMemoryStore`
- `IWebSearchService`

### `src/app/contracts/messages/`

レイヤーをまたいで共有する DTO、イベント、ペイロードを置きます。

- `GeneratedContent`
- `AgentProfileBundle`
- `ChatHistoryItem`
- `ChatToolRequestedPayload`
- `ToolCall`
- `ToolExecutionResult`

### 置き場所の判断

- Domain内部の再利用契約なら `domain/interfaces`
- リポジトリやクエリの契約なら `domain/repositories` または `domain/queries`
- 外部実装に差し替わるサービスなら `contracts/ports`
- 送受信するデータ構造なら `contracts/messages`

---

## バリデーション

### `__post_init__`でのバリデーション

`@dataclass`の`__post_init__`メソッドで不変条件を検証します。

```python
@dataclass
class User:
    id: int
    name: str
    email: str

    def __post_init__(self) -> None:
        """Validate user data."""
        if not self.name:
            raise ValueError("User name cannot be empty.")
        if not self.email:
            raise ValueError("User email cannot be empty.")
        if "@" not in self.email:
            raise ValueError("Invalid email format.")
```

### 複雑なバリデーション

複雑なバリデーションは、専用のメソッドに分離します。

```python
import re


@dataclass
class User:
    EMAIL_REGEX: ClassVar[re.Pattern[str]] = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )

    id: int
    name: str
    email: str

    def __post_init__(self) -> None:
        """Validate user data."""
        self._validate_name()
        self._validate_email()

    def _validate_name(self) -> None:
        """Validate user name."""
        if not self.name:
            raise ValueError("User name cannot be empty.")
        if len(self.name) > 255:
            raise ValueError("User name is too long (max 255 characters).")

    def _validate_email(self) -> None:
        """Validate email format."""
        if not self.email:
            raise ValueError("User email cannot be empty.")
        if not self.EMAIL_REGEX.match(self.email):
            raise ValueError(f"Invalid email format: {self.email}")
```

---

## タイムスタンプ管理（IAuditable）

### IAuditableプロトコル

タイムスタンプ（`created_at`, `updated_at`）を自動管理したいエンティティは、`IAuditable`プロトコルを満たします。

#### 定義

```python
# src/app/domain/interfaces/auditable.py
from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class IAuditable(Protocol):
    """監査時刻を持つ型の契約。"""

    created_at: datetime
    updated_at: datetime
```

#### 実装

```python
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.value_objects import DisplayName, Email, UserId, Version


@dataclass(kw_only=True, slots=True)
class User:
    _id: UserId = field(
        init=False,
        default_factory=lambda: UserId.generate().expect("UserId.generate should succeed"),
    )
    _display_name: DisplayName
    _email: Email
    _version: Version = field(init=False, default_factory=lambda: Version(0))
    _created_at: datetime = field(init=False, default_factory=lambda: datetime.now(UTC))
    _updated_at: datetime = field(init=False, default_factory=lambda: datetime.now(UTC))
```

### タイムスタンプの自動更新

リポジトリ層は更新時に `updated_at` を更新します。`GenericRepository.add()` は集約が持っている初期値をそのまま使い、`GenericRepository.update()` が `IAuditable` と `IVersionable` を見て更新します。

```python
# src/app/infrastructure/repositories/generic_repository.py
async def update(self, entity: T) -> Result[T, RepositoryError]:
    """Update existing entity with optimistic locking support."""
    orm_instance = ORMMappingRegistry.to_orm(entity)

    if isinstance(entity, IAuditable):
        orm_instance.updated_at = datetime.now(UTC)

    if isinstance(entity, IVersionable):
        current_version = entity.version.to_primitive()
        # version をチェックしたうえで更新する
        ...
```

### タイムスタンプ不要なエンティティ

このリポジトリの現行集約はすべて `created_at` / `updated_at` を持ちます。
将来、監査時刻を持たない一時オブジェクトや専用DTOを追加する場合だけ、`IAuditable` を実装しない設計にします。

---

## ベストプラクティス

### 1. ドメインメソッドの命名

ドメインメソッドは**ユビキタス言語（Ubiquitous Language）**を使用します。

✅ **良い例**:

```python
def change_email(self, new_email: Email) -> "User": ...
def change_name(self, new_name: TeamName) -> "Team": ...
def leave(self) -> "TeamMembership": ...
```

❌ **悪い例**:

```python
def update_email(self, email: str) -> "User": ...  # 技術用語
def set_status(self) -> "TeamMembership": ...  # ビジネス意図が不明確
```

### 2. フィールドのデフォルト値

フィールドにデフォルト値を設定する場合は `field(default_factory=...)` を使用します。

✅ **良い例**:

```python
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.value_objects import TeamId, TeamName, Version

@dataclass
class Team:
    _id: TeamId = field(
        init=False,
        default_factory=lambda: TeamId.generate().expect("TeamId.generate should succeed"),
    )
    _name: TeamName
    _version: Version = field(init=False, default_factory=lambda: Version(0))
    _created_at: datetime = field(init=False, default_factory=lambda: datetime.now(UTC))
    _updated_at: datetime = field(init=False, default_factory=lambda: datetime.now(UTC))
```

❌ **悪い例**:

```python
@dataclass
class Team:
    _id: TeamId
    _name: TeamName
    _created_at: datetime = datetime.now(UTC)  # クラス定義時に評価される！
```

### 3. 型ヒントの使用

すべてのフィールドとメソッドに型ヒントを付けます。

```python
from dataclasses import dataclass


@dataclass
class TeamMembership:
    team_id: int
    user_id: int

    def leave(self) -> "TeamMembership":
        """Leave the team."""
        return self
```

### 4. Docstringの記述

公開APIには必ずDocstringを記述します。

```python
@dataclass
class User:
    """User aggregate root.

    Represents a user with display name, email, version, and audit timestamps.
    """
```

### 5. フレームワーク非依存

Domain層はフレームワークに依存しないようにします。

✅ **良い例**:

```python
from dataclasses import dataclass
from datetime import datetime  # 標準ライブラリのみ


@dataclass
class User:
    id: int
    display_name: str
    created_at: datetime
```

❌ **悪い例**:

```python
from sqlmodel import SQLModel, Field  # インフラ層の依存


class User(SQLModel):  # ドメインにインフラが混入！
    id: int
    name: str
```

---

## アンチパターン

### [NG] アンチパターン1: 貧血ドメインモデル（Anemic Domain Model）

ビジネスロジックがない、データだけのクラス。

**悪い例**:

```python
@dataclass
class User:
    """単なるデータ構造"""
    id: int
    name: str
    email: str
    # ビジネスロジックなし
```

**良い例**:

```python
@dataclass
class User:
    """ビジネスロジックを持つ集約"""
    id: int
    name: str
    email: str

    def change_email(self, new_email: str) -> "User":
        """メール変更のビジネスルールを適用"""
        if not self._is_valid_email(new_email):
            raise ValueError("Invalid email format.")
        self.email = new_email
        return self
```

### [NG] アンチパターン2: インフラストラクチャへの依存

Domain層がデータベースやフレームワークに依存している。

**悪い例**:

```python
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Session


class User:
    """ドメインとインフラが混在！"""
    def save(self, session: Session) -> None:
        session.add(self)
        session.commit()
```

**良い例**:

```python
# Domain層: 純粋なビジネスロジック
@dataclass
class User:
    id: int
    name: str

# Infrastructure層: 永続化の責務
class UserRepository:
    async def update(self, user: User) -> Result[User, RepositoryError]:
        # ORM への変換と更新処理
        ...
```

### [NG] アンチパターン3: 神クラス（God Class）

1つのクラスに責務が集中しすぎている。

**悪い例**:

```python
@dataclass
class User:
    """責務が多すぎる"""
    # ユーザー情報
    id: int
    name: str

    # 認証関連
    password_hash: str

    # 注文関連
    memberships: list[TeamMembership]

    # 決済関連
    payment_methods: list[PaymentMethod]

    # ... さらに増え続ける
```

**良い例**:

```python
# 集約を分離
@dataclass
class User:
    """ユーザーの基本情報"""
    id: int
    name: str

@dataclass
class UserCredential:
    """認証情報"""
    user_id: int
    password_hash: str

@dataclass
class TeamMembership:
    """チーム参加情報（別の集約）"""
    id: int
    user_id: int  # Userへの参照はIDのみ
```

---

## まとめ

### Domain層実装のチェックリスト

- [OK] `@dataclass` を使用してシンプルに実装
- [OK] `__post_init__` でバリデーションを実装
- [OK] ビジネスロジックはドメインメソッドに実装
- [OK] フレームワーク非依存を保つ
- [OK] 型ヒントとDocstringを記述
- [OK] タイムスタンプが必要な場合は`IAuditable`を実装
- [OK] 楽観ロックが必要な場合は`IVersionable`を実装
- [OK] 不変条件を常に保証
- [OK] 集約境界を尊重
- [OK] アプリ境界の port は `src/app/contracts/ports/` に置く
- [OK] 共有 DTO / event payload は `src/app/contracts/messages/` に置く
- [NG] データベースアクセスを行わない
- [NG] 外部APIを呼び出さない
- [NG] インフラストラクチャに依存しない

---

## 参考資料

- [プロジェクトのアーキテクチャドキュメント](../architecture/architecture-overview.md)
- [クリーンアーキテクチャ（Robert C. Martin）](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [ドメイン駆動設計（Eric Evans）](https://www.domainlanguage.com/ddd/)
- [Python Protocol（PEP 544）](https://peps.python.org/pep-0544/)
