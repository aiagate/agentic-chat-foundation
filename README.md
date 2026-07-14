# agentic-chat-foundation

`agentic-chat-foundation` は、Discord / LINE のチャネル入口と、周期記憶整理Workerを持つ
agentic chat application foundation です。

単純な Discord Bot の雛形ではなく、チャット入力、AI 推論、tool 実行、返信送信、
長期 memory、検索、DB 永続化をそれぞれ独立した境界で扱うための土台として作られています。

このプロジェクトは現在開発中です。実装、ドキュメント、移行計画は継続的に更新されています。

## 何を作るためのものか

このリポジトリは、次のようなアプリケーションを作るためのテンプレートです。

- Discord DM と LINE webhook の入力を受ける1対1テキスト chatbot
- LLM が提案した外部情報取得を応答作成中に同期実行する workflow
- Web search や memory.read の結果を短期 context として再推論へ戻す応答生成
- SQL raw chat log と Markdown long-term memory を分離した memory system
- Discord / LINE のチャネル処理と、周期的な長期記憶整理を別プロセスとして運用できる構成

## 現在のプロセス構成

Docker Compose では、主に次の process / service を起動します。

- `bot`: Discord Bot process
- `line`: LINE webhook と LINE 返信 sender を持つ FastAPI process
- `worker`: scheduled long-term memory organization を処理する Worker process
- `migrate`: Alembic migration runner
- `postgres`: application database

チャットの返信は、受信したprocess内で受付→応答作成→配信を同期的に完了します。配信に成功した
assistant応答だけをraw chat logへ保存し、次の応答とUC-04の記憶整理で利用します。

## 設計の中心

このプロジェクトは Clean Architecture を基調にし、チャネル入口から共通の会話UseCaseを
同期的に呼び出します。

主な境界は次の通りです。

- `src/app/presentation`: Discord、LINE、Worker の入口と送信処理
- `src/app/usecases`: Command / Query / Handler による application flow
- `src/app/application`: UseCaseから再利用する応答作成の補助サービス
- `src/app/domain`: 会話・記憶に固有のvalue object、repository / query 契約
- `src/app/contracts/ports`: AI、memory、tool、会話送信などの application boundary
- `src/app/contracts/messages`: 会話・AI・memory のDTO
- `src/app/infrastructure`: DB、ORM、AI provider、memory、store、query 実装

アプリケーション境界の契約は `contracts/ports` と `contracts/messages` に置きます。
Domain固有の不変条件に閉じる型は `domain` に置き、複数レイヤーの境界契約は `contracts` に置きます。

## 応答作成

受付済みメッセージについて、履歴・長期記憶・対話相手の設定を読み込み、必要なtool callを
同期実行してから再推論します。応答作成、外部情報取得、配信のいずれかに失敗した場合は、
自動retryや永続待機を行わず、その結果を利用者へ届けます。

## Memory

Memory は raw chat log と long-term memory を分けて扱います。

- SQL database: raw chat log の source of truth
- Markdown memory: Profile、Timeline summary、Entity などの抽象 memory
- Main SQL database: migration 管理された再構築可能な search projection
- PostgreSQL: raw chat logと長期記憶の検索projection

現行の read path は compact な memory manifest 方式です。応答作成では
`memory_id + 1行概要` を system context に注入し、詳細が必要なときだけ本文を読み取ります。

記憶の更新は周期的なUC-04に集約し、raw chatの正本はSQLです。全件rebuild、repair、backupなどの
耐障害性専用処理は業務フローに含めません。

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
- Google Gemini / OpenAI
- Ollama web search adapter
- Ruff / Pyright / pytest

## ドキュメント

詳細は `docs/` 配下に分かれています。

- [アクター別ハイレベルユースケースとユースケース記述](docs/product/application-use-cases.md)
- [ユースケース準拠の一括改修計画](docs/architecture/application-rebuild-plan.md)
- [アーキテクチャ概要](docs/architecture/architecture-overview.md)
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
