# Domain層実装ガイド

最終更新日: 2026-07-14

このプロジェクトのDomain層は、会話と長期記憶に固有の値・不変条件・読み取り契約を表す。
利用者・チーム管理や、耐障害性のための実行状態は業務スコープ外であり、Domain層にも持ち込まない。
業務ユースケースの正本は[ユースケース知識バンドル](../product/application-use-cases/index.md)である。
概念間の関係は[ドメイン図](./domain-diagram.md)にまとめている。

## Domain層の責務

- 外部サービス、ORM、ファイル形式に依存しない値と不変条件を表す
- 会話履歴・長期記憶の読み取りに必要な最小限のQuery契約を定義する
- UseCaseや外部アダプタが共有するDTO・Portは`src/app/contracts`へ置く
- 永続化、AI provider、チャネルSDK、ファイルI/OはInfrastructure層へ委譲する

Domain層は、外部要求を受けるUseCaseではない。受信→応答→配信は
`src/app/usecases/conversation`、周期的な記憶整理は`src/app/usecases/memory`が入口となる。

## 現行の配置

```
src/app/domain/
├── aggregates/     # 会話所有者・関係状態の集約
├── services/       # I/Oを持たないDomain policy
├── queries/        # 履歴・記憶の読み取り契約
├── repositories/   # Domain固有のrepository契約
└── value_objects/  # 会話スコープ、メッセージ内容などの値
```

アプリケーション境界は次の場所に集約する。

```
src/app/contracts/
├── messages/       # IncomingMessage、ConversationResult、memory DTOなど
└── ports/          # ConversationHistory、ResponseGenerator、MemoryStoreなど
```

`contracts/ports`は外部実装へ差し替え可能な境界、`contracts/messages`はレイヤー間で渡すデータを表す。
これらをDomainの汎用インターフェース置き場として重複定義しない。

関係シグナルの全履歴再計算や日次上限のようなI/Oを伴わない業務規則は
`domain/services`の純粋なpolicyで計算する。Repositoryはイベントの置換、保存、楽観ロック、
トランザクションを担い、policyの計算結果を永続化する。

`domain/aggregates/user.py`の`User`は会話・memoryのcanonical ownerであり、Discord/LINEの生IDを
`UserChannelIdentity`として所有する。外部IDからUserを引く境界契約はユースケースから利用するため
`contracts/ports/user_identity_query.py`に置き、SQL実装はinfrastructureに置く。

## 値オブジェクト

値オブジェクトはプリミティブ値の妥当性と変換を一箇所に閉じ込める。生成時に不変条件を検証し、
`from_primitive` / `to_primitive`を備えるものは境界で明示的に変換する。

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MessageContent:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("message content cannot be empty")
```

値オブジェクトへORMや外部SDKの型を渡さない。チャネル固有のIDは会話メッセージの外部識別子として
`contracts/messages/conversation.py`で扱い、内部利用者IDと混同しない。

### 永続化するテキストメッセージ

`MessageContent` の `TEXT` は、単一テキストでも複数テキストでも同じ形式で永続化する。

```json
{
  "type": "TEXT",
  "payload": {
    "texts": ["hello", "follow-up"]
  }
}
```

`payload.text` は廃止済みであり、新規書き込み・読み取りのどちらでも使用しない。
既存行は `202607141500_normalize_message_content_texts.py` で `payload.texts` に変換される。

## Query・Repository契約

Domain固有の読み取り契約だけを`domain/queries`へ置く。実装はInfrastructure層に置き、UseCaseは
`contracts/ports`経由で依存する。

- raw chat logは利用者・会話スコープを必ず指定して読む
- profile、episode、entity/relationshipは同じ利用者スコープで読む
- 書き込み順序やトランザクションはInfrastructureのrepositoryが担う
- Generic Repository、Unit of Workの汎用的な集約変換は作らない

## 不変条件と失敗

不変条件は生成時または責務を持つサービスで検証する。受信・応答・配信・記憶整理の失敗は、
対応するUseCaseの失敗結果として確定する。Domain層にretry、lease、outbox、recovery状態を追加しない。

## 実装・レビュー基準

- すべてのコードに型ヒントを付ける
- 名前は責務を表し、配置と名前を一致させる
- UseCase同士を呼び出さず、共有処理は責務を表すPortまたはServiceへ切り出す
- 追加した抽象が複数レイヤーから参照される場合は`contracts`へ置く
- 変更後は`uv run ruff check .`、`uv run pyright`、`uv run pytest`を実行する
