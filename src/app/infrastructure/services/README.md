# `src/app/infrastructure/services` 棚卸

このディレクトリは、アプリ層のポート実装、LLM/検索アダプタ、Memory 系の一部サービスを置いている。
一方で、`memory_markdown.py` / `memory_decay.py` / `memory_store.py` のような純粋な補助処理は `src/app/infrastructure/memory` 配下へ移動済み。
`tool_result_store.py` は `src/app/infrastructure/stores` 配下へ、`memory_sleep_query_service.py` は `src/app/infrastructure/queries` 配下へ移動済み。
以下は、現時点の各モジュールの責務と利用箇所を棚卸したもの。

## 責務一覧

| モジュール | 主な責務 | 主な利用箇所 | 棚卸メモ |
| --- | --- | --- | --- |
| `gemini_service.py` | Google Gemini を使った `IAIService` 実装。構造化出力を `GeneratedContent` に変換する。 | `src/app/container.py`, `src/app/infrastructure/services/memory_semantic_extraction.py`, `src/app/infrastructure/memory/embedding.py` | OpenAI 系と同じ契約を実装するプロバイダ違いの Service。責務は明確。 |
| `gpt_service.py` | OpenAI Responses API を使った `IAIService` 実装。 | `src/app/container.py` | `GeminiService` と同じ役割で、利用プロバイダだけが異なる。重複ではなく差し替え実装。 |
| `mock_ai_service.py` | テスト/ローカル開発向けのダミー `IAIService` 実装。 | `src/app/container.py`, tests | 生成結果の形を固定するだけで、業務ロジックは持たない。 |
| `ollama_web_search_service.py` | Ollama の web_search API を呼ぶ `IWebSearchService` 実装。 | `src/app/container.py`, `src/app/infrastructure/services/tool_executor.py` | 外部検索アダプタとして単一責務。 |
| `agent_inference_context.py` | memory、profile、tool状態からLLM入力を組み立てる。 | `src/app/container.py`, `src/app/usecases/agent/run_agent_turn.py` | 推論前の入力集約をUseCaseから分離したService。 |
| `tool_completion_notifier.py` | tool完了結果をイベントpayloadへ変換して発行する。 | `src/app/container.py`, `src/app/usecases/agent/handle_tool_execution.py` | イベント表現をUseCaseから分離したNotifier。 |
| `agent_reply_writer.py` | assistant chat と reply-ready Outbox を同一トランザクションで保存する。 | `src/app/container.py`, agent UseCases, tests | 再利用する返信保存をUseCaseから分離したWriter。 |
| `tool_call_router.py` | tool callを検証・短期保存し、実行イベントへ変換する。 | `src/app/container.py`, `src/app/usecases/agent/run_agent_turn.py`, tests | 内部routingをUseCaseから分離したService。 |
| `embedding.py` | Deterministic/Gemini の埋め込み生成実装と、deterministic embedding の補助関数。 | `memory/index_projection.py`, `queries/memory_index_query_service.py`, tests | `DeterministicEmbeddingService` と `GeminiEmbeddingService` は同契約の差し替え実装。 |
| `memory_index_maintenance.py` | Memory index projection の rebuild / repair を担当し、再構築前に既存 snapshot をバックアップする。 | `src/app/container.py`, `src/app/usecases/memory/rebuild_memory_index.py`, `src/app/usecases/memory/repair_memory_index.py`, `memory_consolidation.py`, tests | 検索ではなく更新専用の Service。`queries/memory_index_query_service.py` から分離済み。 |
| `memory_service.py` | `IMemoryService` の実装。検索コンテキスト取得と memory document の読み取りに専念する。 | `src/app/container.py`, `src/app/usecases/agent/run_agent_turn.py`, `tests` | read-only に整理済み。初期 agent プロファイルの作成は write 側の bootstrap に委譲した。 |
| `memory_write_service.py` | プロフィール/エンティティ/タイムラインの書き込みと、初期 agent プロファイルの bootstrap を行う。 | `src/app/container.py`, `tests` | read/write 分離後の write 側。`IMemoryService` から切り離して境界を明確化した。 |
| `memory_semantic_extraction.py` | `IAIService` を使って raw chat log から構造化された memory 更新案を抽出する。 | `src/app/container.py`, `memory_consolidation.py`, tests | LLM へのプロンプト構築と JSON 解析に責務が集中している。 |
| `memory_consolidation.py` | 抽出結果を元に timeline summary を書き込み、entity 参照を更新し、必要なら index を再構築する。 | `src/app/container.py`, `src/app/usecases/memory/run_memory_sleep.py`, tests | 生成結果の反映までを担う orchestration 層。責務はやや広いが、ドメイン的には一塊。 |

## 棚卸の考察

- `GeminiService` / `GptService` / `MockAIService` は同じ `IAIService` 契約を実装しているが、役割は重複していない。プロバイダ差し替えとテスト用スタブであり、統合は不要。
- `DeterministicEmbeddingService` / `GeminiEmbeddingService` も同様に同契約の差し替え実装で、projection構築とランキングから利用する。
- `memory_service.py` は read-only に整理し、書き込みは `memory_write_service.py` に移した。`services` 配下の命名誤認はかなり減ったが、bootstrap の責務は DI 側に残る。
- `memory_write_service.py` は write 専用の補助アダプタとして残る。`IMemoryService` と混ぜないことで、検索系の読み取り経路を薄く保てる。
- 旧memory index portとsidecar utilityは削除済み。projection取得は `queries/memory_index_projection_query.py`、ランキングは `queries/memory_index_query_service.py`、永続化は `repositories/memory_index_repository.py` に分離した。
- `memory_consolidation.py` は semantic extraction の結果をファイルへ反映する orchestration で、`memory_semantic_extraction.py` と責務は連続しているが同一ではない。前者は「反映」、後者は「抽出」。`memory_index` の rebuild まで抱え込まず、maintenance service に委譲する。
- `memory_decay.py` / `memory_markdown.py` / `memory_store.py` は `services` から移動済みで、今は `infrastructure/memory` 配下にある。これで `services` 配下の命名誤認を解消した。
- `tool_result_store.py` は `services` ではなく `infrastructure/stores` に移した。これは一時的な tool result の in-memory 保存であり、Service と呼ぶより Store とする方が責務に合う。
- `memory_sleep_query_service.py` は `services` ではなく `infrastructure/queries` に移した。`run_memory_sleep` のための対象選定ロジックなので、Query 層に置く方が自然。
- `memory_service.py` は `IMemoryIndexQuery` から選定済み文書を受け取り、filesystemを直接走査しない。索引再構築時のMarkdown列挙は `memory/index_projection.py` に限定する。

## 参照

- `src/app/container.py`
- `src/app/usecases/agent/run_agent_turn.py`
- `src/app/usecases/memory/run_memory_sleep.py`
- `src/app/infrastructure/services/tool_executor.py`
