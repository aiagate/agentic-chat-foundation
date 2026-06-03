# LINE メッセージフロー

このドキュメントは、LINE webhook 受信から生成返信の送信までの現行実装
フローを示す。

- LINE FastAPI process は webhook を受け取り、LINE 返信イベントも購読する。
- Worker process は保存済み LINE メッセージイベントを購読し、`RunAgentTurnQuery` を起動する。
- 生成処理は `RetrieveMemoryContextQuery` 経由で記憶コンテキストを取得する。
- 検索が必要な場合も `chat.tool.requested` / `chat.tool.completed` を介する。
- `chat.tool.requested` は `tool_call_id` と `tool_name` を持ち、実際の `ToolCall` は
  `IToolCallStore` 経由で Worker 側が取り出す。
- retrieved context は `tool_call_id` をキーに短期 store へ保存し、再推論時に追加する。
- retrieved context を返す tool call は 1 turn につき 1 件までに抑える。
- reply-ready payload は `contents` を一次情報とする。送信側は `contents` を正として扱い、
  `content` のフォールバックには依存しない。

```mermaid
sequenceDiagram
    autonumber
    actor User as LINEユーザー
    participant LINE as LINE Platform
    participant API as LINE FastAPI process
    participant Mediator as Mediator
    participant SaveUC as SaveLineChatHandler
    participant DB as Chat Repository / UoW
    participant Bus as EventBus
    participant Worker as Worker process
    participant Agent as RunAgentTurnHandler
    participant RouteTool as RouteToolCallsHandler
    participant ToolExec as HandleToolExecutionHandler
    participant WebSearch as RunWebSearchHandler
    participant RetrieveMemory as RetrieveMemoryContextQuery
    participant Memory as IMemoryService
    participant AI as IAIService
    participant Sender as send_line_reply
    participant LINEAPI as AsyncMessagingApi

    User->>LINE: メッセージ送信
    LINE->>API: POST /callback
    API->>Mediator: SaveLineChatCommand(user_id, content)
    Mediator->>SaveUC: handle(command)
    SaveUC->>DB: LineChat.create_user_chat + commit
    SaveUC->>Bus: publish chat.line.saved
    API-->>LINE: OK

    Bus->>Worker: on_line_chat_saved(payload)
    Worker->>Mediator: RunAgentTurnQuery(chat_type=LINE)
    Mediator->>Agent: handle(query)
    Agent->>RetrieveMemory: RetrieveMemoryContextQuery
    RetrieveMemory->>Memory: retrieve(query, user_id)
    Memory-->>RetrieveMemory: MemoryContextPack
    Agent->>AI: generate_content(prompt, history, memory, tool_definitions)

    alt tool call なし
        AI-->>Agent: GeneratedContent(contents)
        Agent->>DB: save assistant message + commit
        Agent->>Bus: publish chat.line.reply_ready(contents)
    else web_search tool call あり
        AI-->>Agent: GeneratedContent(tool_calls)
        Agent->>RouteTool: RouteToolCallsCommand
        RouteTool->>Bus: publish chat.tool.requested
        Bus->>Worker: on_chat_tool_requested(payload)
        Worker->>Mediator: HandleToolExecutionCommand
        Mediator->>ToolExec: handle(command)
        ToolExec->>WebSearch: RunWebSearchCommand(tool_call_id)
        WebSearch->>WebSearch: execute search + save RetrievedContext
        ToolExec->>Bus: publish chat.tool.completed(tool_call_id, status)
        Bus->>Worker: on_chat_tool_completed(payload)
        Worker->>Mediator: RunAgentTurnQuery(tool_call_id)
        Mediator->>Agent: handle(query)
        Agent->>Agent: load retrieved context by tool_call_id
        Agent->>AI: generate_content(prompt, history, memory + retrieved context)
        AI-->>Agent: GeneratedContent(contents)
        Agent->>DB: save assistant message + commit
        Agent->>Bus: publish chat.line.reply_ready(contents)
    end

    Bus->>API: subscribed chat.line.reply_ready
    API->>Sender: send_line_reply(line_bot_api, payload)
    Sender->>LINEAPI: push_message(to=user_id, TextMessage)
    LINEAPI-->>User: 生成返信
```

## EventBus provider の注意点

LINE flow は少なくとも LINE FastAPI process と Worker process に分かれる。`chat.line.saved`
は LINE process から publish され、Worker process が購読する。`chat.line.reply_ready`
は Worker process から publish され、LINE process が購読して `send_line_reply` を実行する。

複数 process で動かす環境では `EVENT_BUS_PROVIDER=redis` または
`EVENT_BUS_PROVIDER=postgres` のように process 間で共有できる provider を設定する。
`memory` provider は同一 process 内でしかイベントを配送できない。
