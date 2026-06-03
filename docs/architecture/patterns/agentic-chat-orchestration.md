# Agentic Chat Orchestration

最終更新日: 2026-06-03

この文書は、LINE / Discord のチャット入力を、LLM と複数 tool を組み合わせた
agentic なワークフローへ流す現在の実装をまとめる。

## 現行の境界

- tool call DTO、agent event payload、event topic は `src/app/contracts/messages`
- `IAIService`、`IEventBus`、`IToolCatalog`、`IToolExecutor`、`IToolCallStore`、
  `IRetrievedContextStore` は `src/app/contracts/ports`
- agent loop の進行、tool request の検証、再推論は `src/app/usecases`
- LINE / Discord の送信処理は `src/app/presentation`
- tool の実行本体、memory 取得、外部 API 呼び出しは `src/app/infrastructure`

`IAIService` は推論境界であり、WebSearch、Memory、LINE、Discord を直接実行しない。
外部機能を実行する責務は、UseCase と adapter に分ける。

## 現行の tool set

`src/app/infrastructure/services/tool_catalog.py` が公開する tool は次の 6 つである。

- `web_search`
- `memory.search`
- `memory.write_candidate`
- `line.reply`
- `discord.reply`
- `discord.post_channel`

`web_search` と `memory.search` は read tool、`memory.write_candidate` は write tool、
`line.reply` / `discord.reply` / `discord.post_channel` は send_message tool である。

## 現行の flow

```text
Saved chat
  └─ presentation/chat handler
      └─ Mediator.send_async(RunAgentTurnQuery)
          └─ usecases/agent/run_agent_turn.py
              ├─ history と memory context を組み立てる
              ├─ agent profile を読み込む
              ├─ IAIService.generate_content(...)
              ├─ tool_calls があれば RouteToolCallsCommand を送る
              └─ reply_ready を publish する

tool request
  └─ usecases/agent/route_tool_calls.py
      ├─ ToolCatalog で検証する
      ├─ tool_call_id を採番する
      ├─ IToolCallStore に保存する
      └─ chat.tool.requested を publish する

tool execution
  └─ presentation/worker/handlers/tool_handlers.py
      ├─ chat.tool.requested を受ける
      ├─ HandleToolExecutionCommand を起動する
      └─ chat.tool.completed を publish する
          └─ usecases/agent/handle_tool_execution.py
              ├─ IToolCallStore から ToolCall を読む
              ├─ IToolExecutor.execute(...)
              └─ generic result を返す

retrieved context replay
  └─ `web_search` と `memory.search` の結果は `tool_call_id` で短期 store に保存する
      └─ `chat.tool.completed` を受けた worker が RunAgentTurnQuery に再入する
```

`RouteToolCallsHandler` は、現行実装では 1 turn あたり 1 件の retrieved-context tool だけを
通す。`RunAgentTurnHandler` は `tool_call_id` があると retrieved context を再投入し、
`web_search` が既に返っている場合は同じ検索を再実行しない。

## 現行の責務

- `RunAgentTurnHandler` は履歴、memory context、agent profile を組み立てて推論する。
- `RouteToolCallsHandler` は tool call を検証し、短期保存して event に変換する。
- `HandleToolExecutionHandler` は tool call を読み出して executor へ渡す。
- `GenericToolExecutor` は tool 名ごとに `web_search`、`memory.search`、
  `memory.write_candidate`、返信系 tool を振り分ける。
- `IRetrievedContextStore` は再推論に必要な短期 context を保持する。

## 共有型

現行で共有される主な型は次のとおり。

- `AgentEnvelope`
- `ToolDefinition`
- `ToolCall`
- `ToolExecutionResult`
- `RetrievedContext`
- `GeneratedContent`
- `ConversationContext`
- `MemoryContextPack`

これらは `contracts/messages` に置き、UseCase 固有の入出力型は `usecases` に残す。

## 参照すべき実装

- `src/app/usecases/agent/run_agent_turn.py`
- `src/app/usecases/agent/route_tool_calls.py`
- `src/app/usecases/agent/handle_tool_execution.py`
- `src/app/infrastructure/services/tool_executor.py`
- `src/app/infrastructure/stores/tool_call_store.py`
- `src/app/infrastructure/stores/retrieved_context_store.py`
