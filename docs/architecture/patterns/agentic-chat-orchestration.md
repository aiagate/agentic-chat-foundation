# Agentic Chat Orchestration

最終更新日: 2026-06-03

この文書は、LINE / Discord のチャット入力を、LLM と複数 tool を組み合わせた
agentic なワークフローへ流す現在の実装をまとめる。

## 現行の境界

- tool call DTO、agent event payload、event topic は `src/app/contracts/messages`
- `IAIService`、`IEventBus`、`IToolCatalog`、`IToolExecutor`、`IToolCallStore`、
  `IToolResultStore` は `src/app/contracts/ports`
- agent loop の進行、tool request の検証、再推論は `src/app/usecases`
- LINE / Discord の送信処理は `src/app/presentation`
- tool の実行本体、memory 取得、外部 API 呼び出しは `src/app/infrastructure`

`IAIService` は推論境界であり、WebSearch、Memory、LINE、Discord を直接実行しない。
外部機能を実行する責務は、UseCase と adapter に分ける。

## 現行の tool set

`src/app/infrastructure/services/tool_catalog.py` が公開する tool は次の 5 つである。

- `web_search`
- `memory.read`
- `memory.write_candidate`
- `line.send`
- `discord.send`

`web_search` と `memory.read` は read tool、`memory.write_candidate` は write tool、
`line.send` / `discord.send` は send_message tool である。

## 現行の flow

```text
Saved chat
  └─ presentation/chat handler
      └─ chat.agent_turn.requested
          └─ Mediator.send_async(RunAgentTurnQuery)
          └─ usecases/agent/run_agent_turn.py
              ├─ history と memory context を組み立てる
              ├─ agent profile を読み込む
              ├─ IAIService.generate_content(...)
              ├─ contents があれば reply_ready を publish する
              └─ tool_calls をすべて RouteToolCallsCommand へ送る

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
              ├─ send_message tool はassistant正本を保存してreply_readyを発行する
              ├─ その他は IToolExecutor.execute(...) を呼ぶ
              └─ generic result を返す

tool result replay
  └─ 非 send tool の結果は `tool_call_id` で短期 store に保存する
      └─ `chat.tool.completed` から `chat.agent_turn.requested` を発行する
```

`RouteToolCallsHandler` は 1 turn の tool call をすべて独立してルーティングする。
各非 send tool の完了は個別に次の agent turn を要求し、結果の集約は行わない。

## 現行の責務

- `RunAgentTurnHandler` は履歴、memory manifest、agent profile を組み立てて推論する。
- `RouteToolCallsHandler` は tool call を検証し、短期保存して event に変換する。
- `HandleToolExecutionHandler` は tool call を読み出し、send_message toolの保存・送信をオーケストレーションする。
- `GenericToolExecutor` は tool 名ごとに `web_search`、`memory.read`、
  `memory.write_candidate` を振り分ける。
- `IToolResultStore` は再推論に必要な全 tool result を保持する。

## 共有型

現行で共有される主な型は次のとおり。

- `AgentEnvelope`
- `ToolDefinition`
- `ToolCall`
- `ToolExecutionResult`
- `ToolResultContext`
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
- `src/app/infrastructure/stores/tool_result_store.py`
