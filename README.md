# agentic-chat-foundation

`agentic-chat-foundation` は、外部の会話チャネルからの入力を受け付け、対話相手との継続的な会話と
長期記憶を扱う agentic chat application foundation です。

単純な chatbot の雛形ではなく、会話の受付、応答作成、結果の通知、長期記憶の整理を
それぞれの業務境界で扱うための土台として作られています。

このプロジェクトは現在開発中です。実装、ドキュメント、移行計画は継続的に更新されています。

## 何を作るためのものか

このリポジトリは、次のようなアプリケーションを作るためのテンプレートです。

- 外部の会話チャネルを通じた1対1のテキスト会話
- 現在の会話、過去の交流から整理された長期記憶、必要な外部情報を用いた応答作成
- 利用者のメッセージの受付、記録、応答、結果の通知
- 会話から人物像、出来事、対象・関係を長期記憶として整理すること
- 複数チャネル上の利用者識別子を一人の利用者へ結び付けること

## 主な能力

- 外部の会話チャネルを通じた1対1のテキスト会話
- 現在の会話、過去の交流から整理された長期記憶、必要な外部情報を用いた応答作成
- 利用者のメッセージの受付、記録、応答、結果の通知
- 会話から人物像、出来事、対象・関係を長期記憶として整理すること
- 複数チャネル上の利用者識別子を一人の利用者へ結び付け、利用者の境界を守ること
- 独立起動した複数のDiscord Botが、共有DBを使わず同じチャンネルで議論すること

会話の受付、応答作成、結果の通知は一つの要求に対する論理的な流れとして扱います。
長期記憶の整理は、利用者の応答とは異なる定期的な契機から行います。

## 設計の中心

このプロジェクトは、外部入口、業務ユースケース、ドメイン概念、技術アダプタを分離する
アーキテクチャを基調にしています。依存方向と境界の詳細は
[アーキテクチャ概要](docs/architecture/architecture-overview.md)で定義します。

## 応答作成

受付済みメッセージについて、会話履歴、長期記憶、対話相手の設定、必要な外部情報を用いて
応答を作成します。応答を作成または届けられない場合は、応答不能の結果として扱います。

## Memory

Memory は会話履歴と長期記憶を分けて扱います。会話履歴は意味を変えない記録、長期記憶は
将来の対話に有用な意味を整理した結果です。長期記憶には人物像、出来事、対象・関係を含め、
それぞれに根拠と不確実性を持たせます。

外部情報は現在の応答の根拠として扱い、取得しただけで長期記憶へ加えません。
複数チャネル上の識別子を同じ利用者へ結び付けた場合も、会話履歴と長期記憶は同じ利用者の境界で扱います。

## ドキュメント

業務上の説明は `docs/product/` と `docs/architecture/`、技術リファレンスは
`docs/infrastructure/` 配下に分かれています。

### 業務・設計

- [ユースケース知識バンドル](docs/product/application-use-cases/index.md)
- [ユビキタス言語バンドル](docs/product/ubiquitous-language/index.md)
- [Discord公開議論バンドル](docs/product/discussion/index.md)
- [アーキテクチャ概要](docs/architecture/architecture-overview.md)

### 技術リファレンス

- [Domain 実装ガイド](docs/domain/domain-implementation-guide.md)
- [ドメイン図](docs/domain/domain-diagram.md)
- [Memory Markdown Schema バンドル](docs/infrastructure/memory-markdown-schema/index.md)
- [User Identity Mapping](docs/infrastructure/user-identity-mapping.md)
- [Autonomous Discord Discussion](docs/infrastructure/discord-autonomous-discussion.md)
- [Memory Write Flow](docs/infrastructure/memory-write-flow.md)
- [Relationship System](docs/infrastructure/relationship-system.md)
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
