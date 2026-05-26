# アーキテクチャ設計ドキュメント

最終更新日: 2026-05-24

このドキュメントは、現行実装に合わせた `discord-bot-template` の
アーキテクチャ境界、プロセス構成、イベント連携、テスト方針を説明します。

---

## アーキテクチャ概要

このプロジェクトはクリーンアーキテクチャを基調にしつつ、外部プロセス間の
連携を `EventBus` で行います。HTTP API、Discord Bot、LINE Webhook、Worker は
同じアプリケーション層を Mediator 経由で呼び出し、永続化や外部サービス連携は
インフラ層に閉じ込めます。

```text
┌─────────────────────────────────────────────────────────────┐
│ Presentation Layer                                          │
│ src/app/presentation/api     FastAPI API                    │
│ src/app/presentation/bot     Discord Bot / Cogs / sender    │
│ src/app/presentation/line    LINE webhook / sender          │
│ src/app/presentation/worker  Event handlers / scheduled job │
├─────────────────────────────────────────────────────────────┤
│ Application Layer                                           │
│ src/app/usecases            Commands / Queries / Handlers   │
│ flow-med Mediator           UseCase dispatch boundary       │
├─────────────────────────────────────────────────────────────┤
│ Contracts Layer                                             │
│ src/app/contracts/ports     Cross-layer interfaces          │
│ src/app/contracts/messages  DTOs / event topics / payloads  │
├─────────────────────────────────────────────────────────────┤
│ Domain Layer                                                │
│ src/app/domain              Aggregates / Value Objects      │
│ src/app/domain/repositories Repository and UoW contracts    │
├─────────────────────────────────────────────────────────────┤
│ Infrastructure Layer                                        │
│ src/app/infrastructure      DB / ORM / repositories         │
│                             AI / memory / EventBus impls    │
│ src/app/container.py        Dependency injection bindings   │
└─────────────────────────────────────────────────────────────┘
```

依存方向は、実装を置く前に必ず確認します。

```text
presentation ──▶ usecases ──▶ domain
      │              │           ▲
      │              │           │
      └────────────▶ contracts ◀─┘
                     ▲
                     │
              infrastructure
```

重要な原則:

- `presentation` は入力の受け取り、出力形式、外部SDKの呼び出しを担当する。
- `presentation` は DB や Unit of Work を直接触らず、Mediator で UseCase を呼ぶ。
- `usecases` はビジネスフロー、トランザクション境界、イベント発行を担当する。
- `domain` は集約と値オブジェクトのルールに集中し、外部技術詳細を知らない。
- `infrastructure` は DB、ORM、AI、メモリ、EventBus 実装を担当する。
- `contracts` は複数レイヤーから参照される境界契約を置く。
- 検索は memory ではなく workflow として扱う。検索要求・検索完了・再推論は
  `contracts/messages` のイベントと短期ストアでつなぎ、`memory_service` には
  raw 検索結果を渡さない。

---

## Contracts Layer

`src/app/contracts` は、ドメイン名や DTO 名ではなく依存方向で配置を決める
共有境界層です。

### ports

`src/app/contracts/ports` には、アプリケーション境界のインターフェースを置きます。

- `ai_service.py`: `IAIService.generate_content(...)`
- `event_bus.py`: `IEventBus.publish/subscribe/start/stop`
- `memory_service.py`: 会話生成で使うメモリ取得・保存境界
- `memory_store.py`, `memory_index.py`, `memory_consolidation.py`,
  `embedding_service.py`: メモリ基盤の抽象

`IAIService` や `IEventBus` は `domain/interfaces` ではなく `contracts/ports` に
置きます。これらは純粋なドメインルールではなく、UseCase、Infrastructure、
Presentation の境界で共有されるアプリケーション契約だからです。

### messages

`src/app/contracts/messages` には、複数レイヤーが共有するDTO、イベントトピック、
ペイロードビルダーを置きます。

- `generated_content.py`: AI 生成結果の構造化DTO `GeneratedContent`
- `chat_events.py`: `chat.discord.saved`, `chat.line.saved`,
  `chat.discord.reply_ready`, `chat.line.reply_ready`,
  `chat.search.requested`, `chat.search.completed` と payload builder
- `memory_context.py`: メモリコンテキストの受け渡しDTO
- `tool_use.py`: LLM の tool request と web search 引数
- `retrieved_context.py`: 検索結果の再投入用 DTO

UseCase 固有の入出力型は `src/app/usecases` に残します。複数レイヤーにまたがる型は
`contracts/messages` に上げ、`usecases` を共有DTO置き場にしません。

---

## Presentation Layer

現行のプレゼンテーション層は4つの入口に分かれています。

### api

`src/app/presentation/api` は FastAPI の管理APIです。

- `__main__.py` の lifespan で DB、DI、Mediator を初期化する。
- `routers/users.py`, `routers/teams.py` は HTTP リクエストを UseCase の
  Command/Query に変換する。
- UseCase の `Result` が失敗した場合は HTTP 例外へ変換する。

### bot

`src/app/presentation/bot` は Discord Bot プロセスです。

- `__main__.py` で DB、DI、Mediator、EventBus を初期化する。
- `cogs/*.py` は Discord イベントやコマンドを受け取り、Mediator で UseCase を呼ぶ。
- `dm_response_cog.py` は DM を `SaveDiscordChatCommand` として保存する。
- `discord_reply_sender.py` は `chat.discord.reply_ready` の payload を Discord へ送る。

Bot プロセスは保存済みメッセージから直接返信を生成しません。返信生成は Worker の
イベントハンドラーに委譲し、Bot 側は返信準備完了イベントを購読して送信します。

### line

`src/app/presentation/line` は LINE Webhook 用 FastAPI プロセスです。

- `__main__.py` の lifespan で DB、DI、Mediator、EventBus を初期化する。
- `/callback` で LINE 署名を検証し、テキストメッセージを
  `SaveLineChatCommand` に変換する。
- `line_reply_sender.py` は `chat.line.reply_ready` の payload を LINE へ送る。

LINE も Discord と同じく、保存と返信生成を分離します。Webhook は保存までを
UseCase に渡し、返信送信は返信準備完了イベントを購読する送信アダプターが担当します。

### worker

`src/app/presentation/worker` は非同期イベント処理と定期ジョブのプロセスです。

- `registry.py` は `@event_handler` と `@scheduled_task` で handler を収集する。
- `handlers.py` は保存済みチャットイベントを受けて `GenerateContentQuery` を実行する。
- `handlers.py` は `RunMemorySleepCommand` を定期実行する。
- `__main__.py` は DB、DI、Mediator、EventBus を初期化し、登録済み handler を
  EventBus に subscribe する。

Worker はプロセス間連携の中心です。外部サービスへ直接返信するのではなく、
返信生成後に `chat.*.reply_ready` を発行し、送信は bot/line 側に戻します。

---

## Multi-process EventBus

`IEventBus` は `src/app/contracts/ports/event_bus.py` に定義されています。
実装は `src/app/infrastructure/messaging` にあります。

- `InMemoryEventBus`: 単一プロセスやローカル開発向け。
- `RedisEventBus`: Redis Pub/Sub による複数プロセス連携。
- `PostgresEventBus`: PostgreSQL LISTEN/NOTIFY による複数プロセス連携。
- `NullEventBus`: handler の単体テストや任意注入なしのフォールバック。

`src/app/container.py` の `MessagingModule` は `EVENT_BUS_PROVIDER` を見て実装を選びます。
未指定の場合は `REDIS_URL` があれば Redis、PostgreSQL の `DATABASE_URL` なら Postgres、
それ以外は memory を選択します。

複数プロセスで bot/line/worker を同時に動かす場合、`InMemoryEventBus` では
プロセスをまたげません。`EVENT_BUS_PROVIDER=redis` または `postgres` を使います。

---

## Chat Flow

Discord DM と LINE は、保存、生成、送信をイベントで分離します。

```text
Discord DM
  └─ presentation/bot/cogs/dm_response_cog.py
      └─ Mediator.send_async(SaveDiscordChatCommand)
          └─ usecases/chat/save_discord_chat.py
              ├─ DB commit
              └─ publish chat.discord.saved

LINE webhook
  └─ presentation/line/__main__.py /callback
      └─ Mediator.send_async(SaveLineChatCommand)
          └─ usecases/chat/save_line_chat.py
              ├─ DB commit
              └─ publish chat.line.saved

worker
  └─ handlers.py
      └─ on_*_chat_saved
          └─ Mediator.send_async(GenerateContentQuery)
              └─ usecases/chat/generate_content.py
                  ├─ recent history query
                  ├─ RetrieveMemoryContextQuery
                  ├─ IAIService.generate_content
                  ├─ tool request 分岐時は chat.search.requested を発行
                  ├─ DB commit assistant message
                  └─ publish chat.*.reply_ready

検索が必要な場合は Worker が `chat.search.requested` と `chat.search.completed`
を介して `usecases/search/*` と `generate_content_with_retrieved_context.py`
を起動し、`retrieved context` を組み込んだ再推論を行う。

sender
  ├─ bot subscribes chat.discord.reply_ready -> send_discord_reply
  └─ line subscribes chat.line.reply_ready -> send_line_reply
```

UseCase は `EventBus` に payload を発行しますが、Discord/LINE SDK の送信処理は
Presentation の sender に閉じます。これにより、アプリケーション層は外部SDKに
依存しません。

---

## Application Layer

`src/app/usecases` は Command/Query と Handler を定義し、`flow-med` の Mediator で
呼び出されます。

代表例:

- `usecases/chat/save_discord_chat.py`: Discord の受信メッセージを保存し、
  `chat.discord.saved` を発行する。
- `usecases/chat/save_line_chat.py`: LINE の受信メッセージを保存し、
  `chat.line.saved` を発行する。
- `usecases/chat/generate_content.py`: 履歴、メモリ、AI サービスを組み合わせて
  assistant メッセージを保存し、返信準備完了イベントを発行する。
- `usecases/chat/generate_content_with_retrieved_context.py`: 検索結果を
  `retrieved context` として再投入し、再推論後の返信を発行する。
- `usecases/search/*`: 検索要求イベントから検索実行と短期ストア保存を行う。
- `usecases/memory/*`: メモリ取得、インデックス更新、睡眠処理を扱う。

Presentation から DB や UoW を直接呼び出す実装は避けます。必要な処理は UseCase として
追加し、Mediator 経由で呼び出します。

---

## Domain Layer

`src/app/domain` は集約、値オブジェクト、ドメイン寄りのリポジトリ/UoW 契約を持ちます。

- `aggregates`: `User`, `Team`, `Chat` などの集約。
- `value_objects`: ID、メールアドレス、チャット種別、メッセージ内容など。
- `repositories`: Repository と Unit of Work の抽象。

ドメイン層はフレームワーク、DB、Discord、LINE、AI SDK、EventBus 実装を知りません。
`domain/interfaces` をアプリケーション全体の契約置き場として再導入しないでください。

---

## Infrastructure Layer

`src/app/infrastructure` は技術詳細を実装します。

- `database.py`: SQLAlchemy/SQLModel の engine と session factory。
- `orm_models`, `orm_mapping.py`, `orm_registry.py`: ORM と Domain の変換。
- `repositories`, `unit_of_work.py`: Repository/UoW 実装。
- `messaging`: `IEventBus` の Redis/Postgres/InMemory 実装。
- `services`: AI provider、メモリストア、メモリインデックス、メモリ統合サービス。

DI は `src/app/container.py` に集約します。新しい実装を追加する場合も、UseCase から
直接具象クラスを import させず、必要な port と DI binding を先に確認します。

---

## Testing

テストは `uv run --frozen pytest` で実行します。非同期テストは `pytest-asyncio` ではなく
`anyio` を方針とします。

```python
import pytest


@pytest.mark.anyio
async def test_usecase() -> None:
    ...
```

`tests/conftest.py` の `anyio_backend` fixture は `asyncio` バックエンドを返します。
これにより anyio の marker を使いながら、実行バックエンドは現在の asyncio 実装に
合わせます。

テストの基本方針:

- 新機能にはテストを追加する。
- バグ修正には回帰テストを追加する。
- UseCase は mocked port または test UoW で境界を検証する。
- EventBus 連携は payload、topic、subscribe の単位で検証する。
- Presentation は外部SDK呼び出しを直接実行せず、sender や app state を mock する。
- DB を使う統合テストは fixture の in-memory SQLite と UoW を使う。

anyio marker が認識されない場合は、pytest plugin autoload を有効化して再実行します。

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD="" uv run --frozen pytest
```

品質チェックの基本順序:

```bash
uv run --frozen ruff format .
uv run --frozen pyright
uv run --frozen ruff check .
uv run --frozen pytest
```

---

## 変更時の配置判断

新しい型やファイルを追加する前に、先に依存方向を明示します。

- 外部SDKや DB の具象実装なら `infrastructure`。
- Discord/LINE/FastAPI/Worker の入口や送信処理なら `presentation`。
- Command/Query/Handler とビジネスフローなら `usecases`。
- 集約や値オブジェクトのルールなら `domain`。
- 複数レイヤーが共有するインターフェースなら `contracts/ports`。
- 複数レイヤーが共有する DTO、イベント名、payload builder なら
  `contracts/messages`。

名前だけで配置しないでください。たとえば `GeneratedContent` は DTO ですが、
AI port、AI service 実装、UseCase が共有する境界型なので `contracts/messages` に置きます。
