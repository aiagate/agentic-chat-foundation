# LINE Message Flow

LINE webhookはチャネル固有のpayloadを共通メッセージへ変換し、3つの会話UseCaseを
同じリクエスト処理内で呼び出す。

```mermaid
sequenceDiagram
    participant LINE
    participant LineApp
    participant UC01 as UC-01 AcceptIncomingMessage
    participant UC02 as UC-02 CreateConversationResponse
    participant UC03 as UC-03 DeliverConversationResult
    participant DB

    LINE->>LineApp: webhook(user id, event id, text)
    LineApp->>UC01: IncomingMessage(channel, conversation, participant, external id)
    UC01->>DB: user raw chat log
    UC01-->>LineApp: AcceptedMessage
    LineApp->>UC02: AcceptedMessage
    UC02->>DB: recent history + long-term memory
    UC02-->>LineApp: ConversationResult
    LineApp->>UC03: ConversationResult + AcceptedMessage
    UC03->>LINE: reply
    UC03->>DB: assistant raw chat log (after successful reply)
```

LINE 1:1の会話識別子は`userId`、受信メッセージの重複判定には`webhookEventId`を使う。
Redis、outbox、AgentRun、lease、retry、recoveryはこのフローの前提にしない。
