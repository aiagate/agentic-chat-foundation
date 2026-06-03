# `src/app/infrastructure/services` 棚卸

このディレクトリは、アプリ層のポート実装、LLM/検索アダプタ、Memory 系の一部サービスを置いている。
一方で、`memory_markdown.py` / `memory_decay.py` / `memory_context_assembler.py` / `memory_store.py` のような純粋な補助処理は `src/app/infrastructure/memory` 配下へ移動済み。
`retrieved_context_store.py` は `src/app/infrastructure/stores` 配下へ、`memory_sleep_query_service.py` は `src/app/infrastructure/queries` 配下へ移動済み。
以下は、現時点の各モジュールの責務と利用箇所を棚卸したもの。

## 責務一覧

| モジュール | 主な責務 | 主な利用箇所 | 棚卸メモ |
| --- | --- | --- | --- |
| `gemini_service.py` | Google Gemini を使った `IAIService` 実装。構造化出力を `GeneratedContent` に変換する。 | `src/app/container.py`, `src/app/infrastructure/services/memory_semantic_extraction.py`, `src/app/infrastructure/memory/embedding.py` | OpenAI 系と同じ契約を実装するプロバイダ違いの Service。責務は明確。 |
| `gpt_service.py` | OpenAI Responses API を使った `IAIService` 実装。 | `src/app/container.py` | `GeminiService` と同じ役割で、利用プロバイダだけが異なる。重複ではなく差し替え実装。 |
| `mock_ai_service.py` | テスト/ローカル開発向けのダミー `IAIService` 実装。 | `src/app/container.py`, tests | 生成結果の形を固定するだけで、業務ロジックは持たない。 |
| `ollama_web_search_service.py` | Ollama の web_search API を呼ぶ `IWebSearchService` 実装。 | `src/app/container.py`, `src/app/usecases/search/run_web_search.py` | 外部検索アダプタとして単一責務。 |
| `embedding.py` | Deterministic/Gemini の埋め込み生成実装と、deterministic embedding の補助関数。 | `queries/memory_index_query_service.py`, `memory_service.py`, `src/app/container.py`, tests | `DeterministicEmbeddingService` と `GeminiEmbeddingService` は同契約の差し替え実装。 |
| `memory_index_maintenance.py` | Memory index projection の rebuild / repair を担当する。 | `src/app/container.py`, `src/app/usecases/memory/rebuild_memory_index.py`, `src/app/usecases/memory/repair_memory_index.py`, `memory_consolidation.py`, tests | 検索ではなく更新専用の Service。`queries/memory_index_query_service.py` から分離済み。 |
| `memory_service.py` | `IMemoryService` の実装。検索コンテキスト取得と memory document の読み取りに専念する。 | `src/app/container.py`, `src/app/usecases/memory/retrieve_memory_context.py`, `tests` | read-only に整理済み。初期 agent プロファイルの作成は write 側の bootstrap に委譲した。 |
| `memory_write_service.py` | プロフィール/エンティティ/タイムラインの書き込みと、初期 agent プロファイルの bootstrap を行う。 | `src/app/container.py`, `tests` | read/write 分離後の write 側。`IMemoryService` から切り離して境界を明確化した。 |
| `memory_semantic_extraction.py` | `IAIService` を使って raw chat log から構造化された memory 更新案を抽出する。 | `src/app/container.py`, `memory_consolidation.py`, tests | LLM へのプロンプト構築と JSON 解析に責務が集中している。 |
| `memory_consolidation.py` | 抽出結果を元に timeline summary を書き込み、entity 参照を更新し、必要なら index を再構築する。 | `src/app/container.py`, `src/app/usecases/memory/run_memory_sleep.py`, tests | 生成結果の反映までを担う orchestration 層。責務はやや広いが、ドメイン的には一塊。 |

## 棚卸の考察

- `GeminiService` / `GptService` / `MockAIService` は同じ `IAIService` 契約を実装しているが、役割は重複していない。プロバイダ差し替えとテスト用スタブであり、統合は不要。
- `DeterministicEmbeddingService` / `GeminiEmbeddingService` も同様に同契約の差し替え実装で、利用箇所は `queries/memory_index_query_service.py` と `memory_service.py` に集約されている。
- `memory_service.py` は read-only に整理し、書き込みは `memory_write_service.py` に移した。`services` 配下の命名誤認はかなり減ったが、bootstrap の責務は DI 側に残る。
- `memory_write_service.py` は write 専用の補助アダプタとして残る。`IMemoryService` と混ぜないことで、検索系の読み取り経路を薄く保てる。
- `memory_index.py` は削除済み。検索は `queries/memory_index_query_service.py`、永続化は `repositories/memory_index_repository.py`、ORM は `orm_models/memory_index_orm.py` に分離した。
- `memory_consolidation.py` は semantic extraction の結果をファイルへ反映する orchestration で、`memory_semantic_extraction.py` と責務は連続しているが同一ではない。前者は「反映」、後者は「抽出」。`memory_index` の rebuild まで抱え込まず、maintenance service に委譲する。
- `memory_context_assembler.py` / `memory_decay.py` / `memory_markdown.py` / `memory_store.py` は `services` から移動済みで、今は `infrastructure/memory` 配下にある。これで `services` 配下の命名誤認を解消した。
- `retrieved_context_store.py` は `services` ではなく `infrastructure/stores` に移した。これは一時的な retrieved context の in-memory 保存であり、Service と呼ぶより Store とする方が責務に合う。
- `memory_sleep_query_service.py` は `services` ではなく `infrastructure/queries` に移した。`run_memory_sleep` のための対象選定ロジックなので、Query 層に置く方が自然。
- 同一責務の重複 Service は見当たらなかった。一方で、`memory_service.py` と `queries/memory_index_query_service.py` には「同じストレージ配下を走査して文書一覧を組み立てる」共通パターンがある。ただし、使う目的が「コンテキスト取得」と「索引再構築」で異なるため、現段階で一本化する必然性は薄い。

## 参照

- `src/app/container.py`
- `src/app/usecases/memory/run_memory_sleep.py`
- `src/app/usecases/memory/retrieve_memory_context.py`
- `src/app/usecases/search/run_web_search.py`
- `src/app/usecases/chat/generate_content_with_retrieved_context.py`
