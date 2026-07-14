# `src/app/infrastructure/services` 棚卸

このディレクトリは、アプリ層のポート実装、LLM/検索アダプタ、Memory 系の一部サービスを置いている。
一方で、`memory_markdown.py` / `memory_decay.py` / `memory_store.py` のような純粋な補助処理は `src/app/infrastructure/memory` 配下へ移動済み。
会話処理は request-local の同期フローで完了し、AgentRun・outbox・tool lease などの状態は保持しない。`long_term_memory_query_service.py` は `src/app/infrastructure/queries` 配下にある。
以下は、現時点の各モジュールの責務と利用箇所を棚卸したもの。

## 責務一覧

| モジュール | 主な責務 | 主な利用箇所 | 棚卸メモ |
| --- | --- | --- | --- |
| `gemini_service.py` | Google Gemini を使った `IAIService` 実装。構造化出力を `GeneratedContent` に変換する。 | `src/app/container.py`, `src/app/infrastructure/services/memory_semantic_extraction.py`, `src/app/infrastructure/memory/embedding.py` | OpenAI 系と同じ契約を実装するプロバイダ違いの Service。責務は明確。 |
| `gpt_service.py` | OpenAI Responses API を使った `IAIService` 実装。 | `src/app/container.py` | `GeminiService` と同じ役割で、利用プロバイダだけが異なる。重複ではなく差し替え実装。 |
| `mock_ai_service.py` | テスト/ローカル開発向けのダミー `IAIService` 実装。 | `src/app/container.py`, tests | 生成結果の形を固定するだけで、業務ロジックは持たない。 |
| `ollama_web_search_service.py` | Ollama の web_search API を呼ぶ `IWebSearchService` 実装。 | `src/app/container.py`, `src/app/infrastructure/services/tool_executor.py` | 外部検索アダプタとして単一責務。 |
| `agent_inference_context.py` | memory、profile、今回のtool結果からLLM入力を組み立てる。 | `src/app/container.py`, `src/app/application/conversation.py` | 推論前の入力集約Service。 |
| `embedding.py` | Deterministic/Gemini の埋め込み生成実装と、deterministic embedding の補助関数。 | `memory/index_projection.py`, `queries/memory_index_query_service.py`, tests | `DeterministicEmbeddingService` と `GeminiEmbeddingService` は同契約の差し替え実装。 |
| `memory_service.py` | `IMemoryService` の実装。検索コンテキスト取得と memory document の読み取りに専念する。 | `src/app/container.py`, `src/app/application/conversation.py`, `tests` | read-only に整理済み。初期プロファイルの作成は write 側の bootstrap に委譲した。 |
| `memory_write_service.py` | プロフィール/エンティティ/タイムラインの書き込みと、初期 agent プロファイルの bootstrap を行う。 | `src/app/container.py`, `tests` | read/write 分離後の write 側。`IMemoryService` から切り離して境界を明確化した。 |
| `memory_semantic_extraction.py` | `IAIService` を使って raw chat log から構造化された memory 更新案を抽出する。 | `src/app/container.py`, `memory_consolidation.py`, tests | LLM へのプロンプト構築と JSON 解析に責務が集中している。 |
| `memory_consolidation.py` | 抽出結果を元に profile、episode、entity/relationship を書き込む。 | `src/app/container.py`, `src/app/usecases/memory/organize_long_term_memory.py`, tests | UC-04の記憶整理を支える反映サービス。検索projectionの全件再構築は行わない。 |

## 棚卸の考察

- `GeminiService` / `GptService` / `MockAIService` は同じ `IAIService` 契約を実装しているが、役割は重複していない。プロバイダ差し替えとテスト用スタブであり、統合は不要。
- `DeterministicEmbeddingService` / `GeminiEmbeddingService` も同様に同契約の差し替え実装で、projection更新とランキングから利用する。
- `memory_service.py` は read-only に整理し、書き込みは `memory_write_service.py` に移した。`services` 配下の命名誤認はかなり減ったが、bootstrap の責務は DI 側に残る。
- `memory_write_service.py` は write 専用の補助アダプタとして残る。`IMemoryService` と混ぜないことで、検索系の読み取り経路を薄く保てる。
- projection取得は `queries/memory_index_projection_query.py`、ランキングは `queries/memory_index_query_service.py`、永続化は `repositories/memory_index_repository.py` に分離する。UC-04では変更された文書だけをupsert/deleteし、全件rebuild、repair、backupは行わない。
- `memory_consolidation.py` は semantic extraction の結果をprofile、episode、entity/relationshipへ反映する orchestration で、`memory_semantic_extraction.py` と責務は連続しているが同一ではない。前者は「反映」、後者は「抽出」。検索projectionの保守処理は持たない。
- `memory_decay.py` / `memory_markdown.py` / `memory_store.py` は `services` から移動済みで、今は `infrastructure/memory` 配下にある。これで `services` 配下の命名誤認を解消した。
- tool call/result は一回の応答作成中だけメモリ上で扱い、PostgreSQLへ実行状態を永続化しない。
- `long_term_memory_query_service.py` は `services` ではなく `infrastructure/queries` に置く。UC-04の対象選定ロジックなので、Query層に置く方が自然。
- `memory_service.py` は `IMemoryIndexQuery` から選定済み文書を受け取り、filesystemを直接走査しない。Markdown列挙は `memory/index_projection.py` に限定する。

## 参照

- `src/app/container.py`
- `src/app/application/conversation.py`
- `src/app/usecases/memory/organize_long_term_memory.py`
- `src/app/infrastructure/services/tool_executor.py`
