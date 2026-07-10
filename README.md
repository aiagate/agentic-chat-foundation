# agentic-chat-foundation

`agentic-chat-foundation` は、Discord / LINE / API / Worker を分離して動かす
agentic chat application foundation です。

単純な Discord Bot の雛形ではなく、チャット入力、AI 推論、tool 実行、返信送信、
長期 memory、検索、DB 永続化をそれぞれ独立した境界で扱うための土台として作られています。

このプロジェクトは現在開発中です。実装、ドキュメント、移行計画は継続的に更新されています。

## 何を作るためのものか

このリポジトリは、次のようなアプリケーションを作るためのテンプレートです。

- Discord DM と LINE webhook の入力を受ける chatbot
- LLM が tool call を提案し、アプリケーション側で検証して実行する agentic workflow
- Web search や memory.read の結果を短期 context として再推論へ戻す応答生成
- SQL raw chat log と Markdown long-term memory を分離した memory system
- Discord / LINE / API / Worker を別プロセスとして運用できる構成

## 現在のプロセス構成

Docker Compose では、主に次の process / service を起動します。

- `bot`: Discord Bot process
- `line`: LINE webhook と LINE 返信 sender を持つ FastAPI process
- `worker`: chat event、tool event、scheduled memory sleep を処理する Worker process
- `migrate`: Alembic migration runner
- `postgres`: application database
- `redis`: cross-process EventBus transport

チャットの返信は 1 つの process で完結させず、保存イベント、agent turn、tool execution、
reply-ready event を経由して送信側 process に戻します。

## 設計の中心

このプロジェクトは Clean Architecture を基調にしつつ、`flow-med` の Mediator と
`IEventBus` で process 間の処理をつなぎます。

主な境界は次の通りです。

- `src/app/presentation`: Discord、LINE、API、Worker の入口と送信処理
- `src/app/usecases`: Command / Query / Handler による application flow
- `src/app/application`: UseCaseから再利用するdurable workflowの状態遷移
- `src/app/domain`: aggregate、value object、repository / query 契約
- `src/app/contracts/ports`: AI、EventBus、memory、tool などの application boundary
- `src/app/contracts/messages`: DTO、event topic、payload builder
- `src/app/infrastructure`: DB、ORM、EventBus、AI provider、memory、store、query 実装

アプリケーション境界の契約は `contracts/ports` と `contracts/messages` に置きます。
`domain/interfaces` は、domain 内で再利用する抽象だけを置く場所です。

## Agentic workflow

LLM は外部機能を直接実行しません。

会話単位の`ConversationCoordinator`と要求単位の`AgentRun`をPostgreSQLへ保存し、
`agent.run.wakeup`で状態機械を進めます。`IAIService`が返した`ToolCall`も
`AgentToolCall`として永続化し、`agent.tool.requested`で実行します。複数toolの結果は
すべて完了してからjoinされ、次turnへまとめて投入されます。

Redisはイベント配送だけを担い、run、tool result、lease、retry状態の正本にはしません。
外部I/O中はDB transactionを保持せず、前後の短いclaim/apply transactionをlease tokenで
保護します。詳細は[Durable Agent Run](docs/architecture/durable-agent-run.md)を参照してください。

## Memory

Memory は raw chat log と long-term memory を分けて扱います。

- SQL database: raw chat log の source of truth
- Markdown memory: Profile、Timeline summary、Entity などの抽象 memory
- Main SQL database: migration 管理された再構築可能な search projection
- PostgreSQL: AgentRun、tool call/result、lease、retryのdurable application state

現行の read path は skills-like な manifest 方式です。Agent turn では compact な
`memory_id + 1行概要` を system context に注入し、詳細が必要になったときだけ
`memory.read(memory_id)` で本文を取り出します。

現行実装では、`memory.write_candidate` が raw Timeline Markdown を書く経路も残っています。
これは移行中の動作であり、raw chat の正本は SQL です。

## 技術要素

- Python 3.13
- `uv`
- `discord.py`
- FastAPI
- LINE Bot SDK
- `flow-med` / `flow-res`
- `injector`
- SQLModel / SQLAlchemy / Alembic
- PostgreSQL / SQLite
- Redis
- Google Gemini / OpenAI
- Ollama web search adapter
- Ruff / Pyright / pytest

## ドキュメント

詳細は `docs/` 配下に分かれています。

- [アーキテクチャ概要](docs/architecture/architecture-overview.md)
- [イベント呼び出しグラフ](docs/architecture/event-call-graph.md)
- [Durable Agent Run](docs/architecture/durable-agent-run.md)
- [Agentic Chat Orchestration](docs/architecture/patterns/agentic-chat-orchestration.md)
- [LLM Web Search Orchestration](docs/architecture/patterns/llm-web-search-orchestration.md)
- [Domain 実装ガイド](docs/domain/domain-implementation-guide.md)
- [Memory Markdown Schema](docs/infrastructure/memory-markdown-schema.md)
- [Memory Write Flow](docs/infrastructure/memory-write-flow.md)
- [Database Migrations](docs/infrastructure/database-migrations.md)

## 開発時の前提

起動と運用は Docker Compose を前提にしています。
コード変更後はコンテナを再ビルドして再起動します。

```bash
docker compose up --build -d
```

依存管理と検証コマンドは `uv` を使います。
詳細な開発ルールは [AGENTS.md](AGENTS.md) と `docs/` の各設計文書を参照してください。

## License

This project is licensed under the [MIT License](LICENSE).
