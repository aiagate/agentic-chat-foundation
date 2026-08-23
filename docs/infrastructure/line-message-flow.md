# LINE Message Flow

> 本書はLINE固有の入力変換と結果通知を扱う技術リファレンスである。業務上の受付・応答・通知の意味は
> [ユースケース](../product/application-use-cases/index.md)を正本とする。

LINE webhookはチャネル固有のpayloadを共通メッセージへ変換し、3つの会話ユースケースを
同じリクエスト処理内で呼び出す。

```mermaid
sequenceDiagram
    participant LINE
    participant LineApp
    participant Intake as メッセージを受け付ける
    participant Response as 会話への応答を作成する
    participant Delivery as 応答結果を利用者へ届ける
    participant Identity as User identity query
    participant DB

    LINE->>LineApp: webhook(user id, event id, text)
    LineApp->>Intake: IncomingMessage(channel, conversation, participant, external id)
    Intake->>Identity: (line, source.user_id)
    Identity-->>Intake: canonical User / 未登録
    Intake->>DB: user raw chat log
    Intake-->>LineApp: AcceptedMessage
    LineApp->>Response: AcceptedMessage
    Response->>DB: recent history + long-term memory
    Response-->>LineApp: ConversationResult
    LineApp->>Delivery: ConversationResult + AcceptedMessage
    Delivery->>LINE: reply
    Delivery->>DB: assistant raw chat log (after successful reply)
```

LINE 1:1の会話識別子は`userId`、受信メッセージの重複判定には`webhookEventId`を使う。
`source.user_id`が`user_channel_identities`に未登録なら、raw chat保存前に受付を失敗させる。
Redis、outbox、AgentRun、lease、永続的なretry/recovery状態はこのフローの前提にしない。
