# LLM Web Search Orchestration

この文書は、LLM が要求した `web_search` を現在の generic tool flow で実行し、
検索結果を再推論へ渡す実装をまとめる。

## Scope and boundaries

- `IAIService` は検索を実行しない。
- LLM は `GeneratedContent.tool_calls` として `ToolCall` を返す。
- `web_search` は `chat.tool.requested` / `chat.tool.completed` を通る。
- tool result の参照キーは `tool_call_id` とする。
- `chat.search.requested` / `chat.search.completed` は使わない。

## 現行の flow

1. `RunAgentTurnHandler` が履歴、memory context、agent profile を集める
2. `IAIService.generate_content(...)` に tool definitions を渡して推論する
3. 推論結果が `tool_calls` を含む場合、`RouteToolCallsHandler` が検証して `chat.tool.requested` を発行する
4. `tool_handlers.py` が `chat.tool.requested` を受け、`HandleToolExecutionCommand` を起動する
5. `HandleToolExecutionHandler` が `tool_call_id` から `ToolCall` を取得し、`GenericToolExecutor` が `web_search` を実行する
6. `GenericToolExecutor` が `ToolResultContext` を `tool_call_id` で短期 store に保存する
7. `HandleToolExecutionHandler` が `chat.tool.completed` を発行する
8. `tool_handlers.py` が `chat.tool.completed` を `chat.agent_turn.requested` に変換する
9. 共通 handler が `tool_call_id` 付きで `RunAgentTurnQuery` を起動し、tool resultを再投入する
10. 最終応答を保存し、`chat.*.reply_ready` を発行する

## DTO

```python
class ToolCall(AgentEnvelope):
    tool_name: str
    arguments: dict[str, object]


class ToolResultContext(BaseModel):
    tool_call_id: str
    tool_name: str
    status: Literal["ok", "error"]
    result: dict[str, object]
    rendered_text: str


class GeneratedContent(AgentEnvelope):
    contents: list[str]
    tool_calls: list[ToolCall]
```

`tool_call_id` は `RouteToolCallsHandler` で未設定なら採番する。
以降の tool request、tool completed、tool result store の正本キーはこの ID である。
`RouteToolCallsHandler` は全 tool call を独立してルーティングする。

## 現行の補足

- `RunAgentTurnHandler` は tool result を再投入する。
- 検索結果は短期 context であり、raw のまま long-term memory に保存しない。
- 長期記憶へ昇格するのは、再利用価値が高く、安定した知識として抽出された内容に限る。
