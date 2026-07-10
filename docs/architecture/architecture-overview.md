# Architecture Overview

## 依存方向

```text
presentation -> usecases -> application -> contracts/domain
                    infrastructure -> contracts/domain
```

- `presentation`: Discord、LINE、API、Workerのadapter。
- `usecases`: 外部要求ごとのCommand/Query入口。1 module 1 Handler。
- `application`: 複数stepを持つAgent固有のオーケストレーション。
- `contracts/ports`: AI、tool、UoWなどのapplication boundary。
- `contracts/messages`: layerをまたぐDTO、topic、payload builder。
- `domain`: chat等のaggregate、value object、domain固有の抽象。
- `infrastructure`: PostgreSQL、Redis、AI、memory、external APIの実装。

UseCase同士は呼び出さない。再利用する進行ロジックは`application`へ置き、
infrastructureとpresentationへ依存させない。fitness testでこの方向を固定する。

## プロセス

- `bot`: Discord入力とreply-readyの送信。
- `line`: LINE webhook入力とreply-readyの送信。
- `worker`: Outbox配送後のイベント購読、Agent/tool実行、lease復旧、memory sleep。
- `migrate`: Alembic migration。
- `postgres`: domainデータ、Outbox、durable application stateの正本。
- `redis`: process間event transport。workflow stateの正本ではない。

## Chat acceptance

`SaveDiscordChatHandler` / `SaveLineChatHandler`は、chat rowと`chat.*.saved` Outboxを
同一transactionで保存する。Workerの`StartAgentRunHandler`はsource chat idで
idempotentにrunを受理し、会話mailboxが空いている場合だけwakeupを作る。

会話keyは次の要素から作る。

```text
character_id + chat_type + platform conversation id
```

Discordのconversation idはguild/channel、LINE 1:1はuser idである。chat idはmessage id
なのでserialization keyには使わない。

## Durable Agent workflow

`ConversationCoordinator`、`AgentRun`、`AgentToolCall`をPostgreSQLへ保存する。
Run coordinatorはclaim transactionで短いleaseを取得し、transactionを閉じてから
履歴/memory取得とLLM推論を行い、別のapply transactionで結果を反映する。

```text
queued -> ready -> running -> waiting_for_tools -> ready
                         \-> retry_wait -> ready
                         \-> completed / failed / cancelled
```

LLMがcontentsを返した場合、assistant chat、reply-ready Outbox、run状態をatomicに保存する。
ToolCallを返した場合、catalogで検証してdurable rowとtool requested Outboxを保存する。
複数toolは全件terminalになった時だけ最後の完了transactionがrunをreadyへ戻す。

配送topicは`agent.run.wakeup`と`agent.tool.requested`だけであり、payloadはdurable idと
sequence/attemptだけを持つ。古い配送は状態条件が一致せずno-opになる。

30秒ごとのrecovery scanが期限切れleaseと期限到来retryを再配送可能にする。
`app.error.detected`は観測専用で、workflowを再起動しない。

詳細は[Durable Agent Run](durable-agent-run.md)と
[Event Call Graph](event-call-graph.md)を参照する。

## Tool boundary

`IToolCatalog`は定義と制限、`IToolExecutor`は外部実行を担当する。永続化とjoinは
`AgentRunRepository`が担当し、executorはRedis storeやEventBusを知らない。

`web_search`、`memory.read`、`memory.write_candidate`は次turnへ結果を戻す。
`line.send` / `discord.send`は単独callかつterminalである。

## Memory

raw chatの正本はPostgreSQL、長期memory documentはMarkdown、検索projectionはmain SQL DBに
分離する。Markdown更新はtemp fileをflushして`os.replace`するatomic replacementを使う。
Agent推論は`IMemoryService`のretrieval boundaryだけを参照し、pathやMarkdown形式を知らない。

## Transactional Outbox

外部processへ渡すイベントはbusiness writeと同じtransactionでOutboxへ追加する。
dispatcherがclaim/publish/markを行うため、DB commit後・publish前のprocess停止から復旧できる。
consumer側でもsequence、attempt、source idによるidempotencyを必須とする。
