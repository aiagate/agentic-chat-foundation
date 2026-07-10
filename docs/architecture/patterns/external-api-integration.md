# 外部API連携パターン

この文書は、現在の実装に合わせた外部 API 連携の境界をまとめる。
重要なのは、外部 API の都合を `usecases` や `domain` に漏らさないことです。

## 現行の分離

外部 API 連携は次の 3 層に分ける。

| 層 | 役割 | 現行の置き場 |
| :--- | :--- | :--- |
| `contracts/ports` | 利用側が依存する契約 | `src/app/contracts/ports/ai_service.py`、`web_search_service.py` |
| `infrastructure/services` | 外部 API アダプタ | `src/app/infrastructure/services/gpt_service.py`、`gemini_service.py`、`ollama_web_search_service.py` |
| `usecases` | 契約を使う側 | `src/app/usecases/agent/run_agent_turn.py` |

`src/app/domain/interfaces/` は、Domain 内で再利用する抽象だけに使う。
アプリケーション全体の境界契約を置く場所ではない。

## 現行の具体例

### LLM provider

- 契約: `src/app/contracts/ports/ai_service.py`
- 実装: `src/app/infrastructure/services/gemini_service.py`
- 実装: `src/app/infrastructure/services/gpt_service.py`
- テスト/開発用実装: `src/app/infrastructure/services/mock_ai_service.py`

`IAIService` は `GeneratedContent` を返し、web search や message send を直接実行しない。

### Web search

- 契約: `src/app/contracts/ports/web_search_service.py`
- tool実行: `src/app/infrastructure/services/tool_executor.py`
- 外部API実装: `src/app/infrastructure/services/ollama_web_search_service.py`

検索結果は長期 memory ではなく、`tool_call_id` で短期 retrieved context として扱う。

### Memory / tool write candidate

- memory 読み取り契約: `src/app/contracts/ports/memory_service.py`
- memory 書き込み契約: `src/app/contracts/ports/memory_write_service.py`
- memory 実装: `src/app/infrastructure/services/memory_service.py`
- memory write 実装: `src/app/infrastructure/services/memory_write_service.py`

`memory.write_candidate` は現行実装では `IMemoryWriteService` を通して
raw Timeline Markdown を書く candidate path として残っている。

### Agentic tool flow

- tool DTO: `src/app/contracts/messages/tool_contracts.py`
- tool event: `src/app/contracts/messages/chat_events.py`
- tool router: `src/app/infrastructure/services/tool_call_router.py`
- tool execution: `src/app/usecases/agent/handle_tool_execution.py`

`ToolCallRoutingService` で検証した tool call を `chat.tool.requested` に変換し、
`GenericToolExecutor` で実行して `chat.tool.completed` に戻す。

## 置き場の判断

新しい外部連携を追加するときは、次の順で置き場を決める。

1. 境界契約なら `contracts/ports`
2. レイヤーをまたぐ DTO やイベントなら `contracts/messages`
3. 外部 SDK を叩く具象なら `infrastructure/services`
4. Domain の不変条件に閉じる抽象だけなら `domain/interfaces`

## この文書の役割

この文書は、古い movie service の例の代わりに、現在のリポジトリが採用している
外部連携の配置ルールを示すためのものとする。
