# Domain層ドキュメント

このディレクトリには、Domain層の設計と実装に関するドキュメントがあります。

## どこに何を置くか

- `src/app/domain/aggregates/`: `User`、`Team`、`Chat`、`TeamMembership` などの集約
- `src/app/domain/value_objects/`: `UserId`、`DisplayName`、`Email`、`Version` などの値オブジェクト
- `src/app/domain/interfaces/`: ドメイン内で再利用する契約
- `src/app/domain/repositories/`: リポジトリと Unit of Work の契約
- `src/app/domain/queries/`: 読み取り専用クエリの契約
- `src/app/contracts/ports/`: アプリケーション境界の port 契約
- `src/app/contracts/messages/`: レイヤー間で共有する DTO、イベント、ペイロード

`domain/interfaces` は、アプリ境界の port を置く場所ではありません。`IAuditable`、`IValueObject`、`IVersionable` のような、ドメインモデルと永続化層の両方から使う再利用契約だけを置きます。

## ドキュメント一覧

### [Domain実装ガイド](./domain-implementation-guide.md)

Domain層の実装方針、契約の置き場所、集約の書き方、永続化との境界をまとめたガイドです。

主な内容:

- Domain層の役割と責務
- `domain/interfaces`、`domain/repositories`、`contracts/ports`、`contracts/messages` の使い分け
- 集約の実装パターン
- 値オブジェクトとバリデーション
- 監査時刻と楽観ロックの扱い
- 実装上のアンチパターン

対象読者:

- 新しいドメイン型を追加する開発者
- Domain層のレビューを行う開発者
- 契約の配置を確認したい開発者

## すぐ使う例

### 新しい集約を作る

実装の基準は `src/app/domain/aggregates/user.py` と `src/app/domain/aggregates/team_membership.py` です。

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
```

### 境界の契約を置く

- `src/app/contracts/ports/agent_profile_service.py`: `IAgentProfileService`
- `src/app/contracts/messages/generated_content.py`: `GeneratedContent`
- `src/app/contracts/messages/chat_events.py`: `build_*_payload` 系のイベントペイロード

アプリ境界の契約は `domain/interfaces` ではなく `contracts/ports` と `contracts/messages` に置きます。

## 関連ドキュメント

- [Domain実装ガイド](./domain-implementation-guide.md)
- [アーキテクチャ概要](../architecture/architecture-overview.md)

## ヒント

- Domain層は純粋なPythonオブジェクトに保つ
- 値オブジェクトは `from_primitive` / `to_primitive` を実装する
- 監査時刻と楽観ロックは `GenericRepository` と `Version` の実装に合わせる
- アプリ境界の DTO や port を domain 配下に混ぜない

## FAQ

**Q: `IAuditable` はどこで使う？**

A: `src/app/infrastructure/repositories/generic_repository.py` の `update()` が、`IAuditable` を持つ集約の `updated_at` を更新します。

**Q: `contracts/messages` には何を置く？**

A: `GeneratedContent`、`AgentProfileBundle`、`ChatToolRequestedPayload` のような、複数レイヤーで共有するデータ構造を置きます。

**Q: `contracts/ports` には何を置く？**

A: `IAgentProfileService`、`IMemoryStore`、`IAIService` のような、外部実装に差し替わるサービス契約を置きます。

最終更新日: 2026-06-03
