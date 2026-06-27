# アーキテクチャ設計ドキュメント

最終更新日: 2026-06-03

このドキュメントは、現在の実装に合わせた `agentic-chat-foundation` の
アーキテクチャ境界、プロセス構成、イベント連携を説明します。

---

## アーキテクチャ概要

このリポジトリはクリーンアーキテクチャを基調にしつつ、チャット入力から返信までを
`flow-med` の Mediator と `EventBus` でつなぎます。現在の実装では、外部連携の
境界は `src/app/contracts/ports`、共有 DTO とイベント定義は
`src/app/contracts/messages` に置きます。

```text
┌─────────────────────────────────────────────────────────────┐
│ Presentation                                                │
│ src/app/presentation/api     FastAPI API                   │
│ src/app/presentation/bot     Discord Bot / senders         │
│ src/app/presentation/line    LINE webhook / senders        │
│ src/app/presentation/worker  Event handlers / schedulers   │
├─────────────────────────────────────────────────────────────┤
│ Application                                                 │
│ src/app/usecases            Commands / Queries / Handlers  │
│ flow-med Mediator           UseCase dispatch boundary      │
├─────────────────────────────────────────────────────────────┤
│ Contracts                                                   │
│ src/app/contracts/ports     Cross-layer interfaces         │
│ src/app/contracts/messages  DTOs / events / payloads       │
├─────────────────────────────────────────────────────────────┤
│ Domain                                                      │
│ src/app/domain              Aggregates / value objects     │
│ src/app/domain/interfaces   Domain-specific abstractions   │
├─────────────────────────────────────────────────────────────┤
│ Infrastructure                                              │
│ src/app/infrastructure      DB / ORM / repositories        │
│                             queries / stores / services    │
│ src/app/container.py        Dependency injection bindings  │
└─────────────────────────────────────────────────────────────┘
```

依存方向は次の前提で固定します。

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

- `presentation` は入力の受け取り、送信、外部 SDK の薄い呼び出しを担う。
- `presentation` は DB や UoW を直接触らず、Mediator で UseCase を呼ぶ。
- `usecases` はビジネスフロー、トランザクション境界、イベント発行を担う。
- `domain` は集約、値オブジェクト、ドメイン固有の抽象に集中する。
- `contracts/ports` はアプリケーション境界の共有インターフェースを置く。
- `contracts/messages` は複数レイヤーで共有する DTO、イベント、payload を置く。
- `infrastructure` は DB、ORM、検索、ストア、AI、EventBus の実装を持つ。
- 検索や tool 実行は、`tool_call_id` をキーに短期ストアとイベントで再入する。
- LLM は外部機能を直接実行せず、UseCase と adapter が検証して実行する。

関連する設計文書:

- [Agentic Chat Orchestration](patterns/agentic-chat-orchestration.md)
- [LLM Web Search Orchestration](patterns/llm-web-search-orchestration.md)

---

## Contracts Layer

`src/app/contracts` は、依存方向に基づいて配置を決める共有境界です。

### ports

`src/app/contracts/ports` には、アプリケーション境界のインターフェースを置きます。

現在の主な port:

- `ai_service.py`: `IAIService.generate_content(...)`
- `event_bus.py`: `IEventBus.publish/subscribe/start/stop`
- `agent_profile_service.py`: エージェント用プロフィール束の読み込み
- `memory_service.py`: 会話用メモリの取得
- `memory_write_service.py`: メモリ候補の書き込み
- `tool_catalog.py`: 利用可能 tool 定義の列挙
- `tool_executor.py`: 検証済み tool call の実行
- `tool_call_store.py`: tool call の短期保存
- `tool_result_store.py`: tool result の短期保存
- `web_search_service.py`: 外部 web search の実行

`IAIService` や `IEventBus` のようなアプリケーション境界の契約は、
`domain/interfaces` ではなく `contracts/ports` に置きます。
`domain/interfaces` は、`versionable.py` や `auditable.py` のような
ドメイン固有の抽象だけに使います。

### messages

`src/app/contracts/messages` には、複数レイヤーで共有する DTO とイベント定義を置きます。

現在の主な message:

- `agentic.py`: `AgentEnvelope`
- `chat_events.py`: `chat.discord.saved`、`chat.line.saved`、
  `chat.agent_turn.requested`、`chat.tool.requested`、`chat.tool.completed`、
  `chat.discord.reply_ready`、`chat.line.reply_ready`
- `tool_contracts.py`: `ToolDefinition`、`ToolCall`、`ToolExecutionResult`
- `tool_result_context.py`: `ToolResultContext`
- `generated_content.py`: AI 生成結果 DTO
- `memory_context.py`: メモリコンテキスト DTO
- `agent_profile.py`: `AgentProfileBundle`
- `conversation_context.py`: 会話コンテキスト DTO
- `memory_index.py`: memory index projection の DTO

UseCase 固有で共有価値が低い型は `usecases` に残します。
複数レイヤーにまたがる型を `usecases` に置きっぱなしにしません。

---

## Presentation Layer

現在のプレゼンテーション層は 4 つの入口です。

### api

`src/app/presentation/api` は FastAPI の管理 API です。

- `__main__.py` の lifespan で DB、DI、Mediator を初期化する。
- `routers/users.py`、`routers/teams.py` は HTTP リクエストを UseCase に変換する。

### bot

`src/app/presentation/bot` は Discord Bot プロセスです。

- `cogs/dm_response_cog.py` は受信 DM を保存 UseCase に渡す。
- `discord_reply_sender.py` は `chat.discord.reply_ready` を Discord へ送る。

### line

`src/app/presentation/line` は LINE webhook プロセスです。

- `__main__.py` の `/callback` で署名検証と保存 UseCase への変換を行う。
- `line_reply_sender.py` は `chat.line.reply_ready` を LINE へ送る。

### worker

`src/app/presentation/worker` はイベント処理と定期ジョブのプロセスです。

- `handlers/chat_reply_handlers.py` は保存済みチャットから `RunAgentTurnQuery` を起動する。
- `handlers/tool_handlers.py` は `chat.tool.requested` と `chat.tool.completed` を扱う。
- `handlers/memory_sleep_handlers.py` は `RunMemorySleepCommand` を定期実行する。
- `handlers/app_error_handlers.py` は失敗時の再実行を扱う。
- `handlers/user_handlers.py` は `user.created` を扱う。

Worker は返信そのものを送信しません。返信内容は `chat.*.reply_ready` として
bot/line 側の sender に戻します。

---

## EventBus

`IEventBus` は `src/app/contracts/ports/event_bus.py` に定義されています。
実装は `src/app/infrastructure/messaging` にあります。

- `InMemoryEventBus`: 単一プロセスやローカル開発向け。
- `RedisEventBus`: Redis Pub/Sub による複数プロセス連携。
- `PostgresEventBus`: PostgreSQL LISTEN/NOTIFY による複数プロセス連携。
- `NullEventBus`: ハンドラの単体テスト向けフォールバック。

`src/app/container.py` は `EVENT_BUS_PROVIDER`、`REDIS_URL`、`DATABASE_URL`
を見て実装を選びます。

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
  └─ handlers/chat_reply_handlers.py
      └─ publish chat.agent_turn.requested
          └─ Mediator.send_async(RunAgentTurnQuery)
          └─ usecases/agent/run_agent_turn.py
              ├─ history と memory context を組み立てる
              ├─ IAIService.generate_content(...)
              ├─ contents があれば assistant message を保存して reply_ready を publish
              └─ tool_calls をすべて RouteToolCallsCommand へ送る

tool flow
  └─ usecases/agent/route_tool_calls.py
      ├─ tool call を検証する
      ├─ IToolCallStore に保存する
      └─ chat.tool.requested を publish する
      └─ worker/handlers/tool_handlers.py
          ├─ HandleToolExecutionCommand を起動する
          ├─ IToolExecutor.execute(...)
              └─ chat.tool.completed を publish する
              └─ 非 send tool は tool result を保存して
                 chat.agent_turn.requested を発行する

sender
  ├─ bot subscribes chat.discord.reply_ready -> send_discord_reply
  └─ line subscribes chat.line.reply_ready -> send_line_reply
```

`RunAgentTurnHandler` は、`tool_call_id` がある場合に対応する tool result を再投入します。

---

## Application Layer

`src/app/usecases` は Command / Query / Handler を定義し、Mediator から呼び出されます。

代表例:

- `usecases/chat/save_discord_chat.py`: Discord の受信メッセージを保存する。
- `usecases/chat/save_line_chat.py`: LINE の受信メッセージを保存する。
- `usecases/agent/run_agent_turn.py`: 履歴、メモリ、AI サービスを組み合わせて返信を生成する。
- `usecases/agent/route_tool_calls.py`: tool call を検証して `chat.tool.requested` を発行する。
- `usecases/agent/handle_tool_execution.py`: `tool_call_id` を正本に tool を実行して `chat.tool.completed` を発行する。
- `usecases/search/run_web_search.py`: web search を実行して tool result を返す。
- `usecases/memory/*`: メモリ取得、インデックス更新、睡眠処理を扱う。

Presentation から DB や UoW を直接呼び出す実装は避けます。

---

## Domain Layer

`src/app/domain` は集約、値オブジェクト、ドメイン固有の抽象を持ちます。

- `aggregates`: `User`、`Team`、`Chat` などの集約。
- `value_objects`: ID、メールアドレス、チャット種別、メッセージ内容など。
- `interfaces`: ドメイン固有の抽象のみ。
- `repositories`: Repository と Unit of Work の抽象。

ドメイン層はフレームワーク、DB、Discord、LINE、AI SDK、EventBus 実装を知りません。
アプリケーション境界の契約を `domain/interfaces` に戻さないでください。

---

## Infrastructure Layer

`src/app/infrastructure` は技術詳細を実装します。

- `database.py`: SQLAlchemy の engine と session factory。
- `orm_models`、`orm_mapping.py`、`orm_registry.py`: ORM と Domain の変換。
- `repositories`: 永続化リポジトリ実装。
- `queries`: 読み取り、選定、再構成ロジック。
- `stores`: tool call と tool result の短期ストア。
- `services`: AI provider、memory service、tool executor、tool catalog などの adapter。
- `memory`: Markdown memory の低レベル I/O と補助処理。
- `messaging`: `IEventBus` の実装。

DI は `src/app/container.py` に集約します。UseCase から具象クラスを直接 import せず、
必要な port と binding を先に確認します。

---

## Testing

テストは `uv run --frozen pytest` で実行します。非同期テストは `anyio` を方針とします。

```python
import pytest


@pytest.mark.anyio
async def test_usecase() -> None:
    ...
```

テストの基本方針:

- 新機能にはテストを追加する。
- バグ修正には回帰テストを追加する。
- UseCase は mocked port または test UoW で境界を検証する。
- EventBus 連携は payload、topic、subscribe の単位で検証する。
- Presentation は外部 SDK 呼び出しを直接実行せず、sender や app state を mock する。
- DB を使う統合テストは fixture の in-memory SQLite と UoW を使う。

品質チェックの基本順序:

```bash
uv run --frozen ruff format .
uv run --frozen pyright
uv run --frozen ruff check .
uv run --frozen pytest
```

---

## 変更時の配置判断

新しい型やファイルを追加する前に、依存方向を明示します。

- 外部 SDK や DB の具象実装なら `infrastructure`。
- Discord / LINE / FastAPI / Worker の入口や送信処理なら `presentation`。
- Command / Query / Handler とビジネスフローなら `usecases`。
- 集約や値オブジェクトのルールなら `domain`。
- 複数レイヤーが共有するインターフェースなら `contracts/ports`。
- 複数レイヤーが共有する DTO、イベント名、payload builder なら `contracts/messages`。
