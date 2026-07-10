# Durable Agent Run

## 決定

Cloudflare Workersへ載せること自体は目的にせず、Durable Objectsの「IDごとの直列化」と
Workflowsの「永続step、retry、復旧」をアプリケーション設計として採用する。
PostgreSQLを状態の正本、transactional Outboxを配送境界、Redisを交換可能なtransportとする。

依存方向は次の通りとする。

`presentation -> usecases -> application -> contracts/domain`

`infrastructure`はcontracts/domainのportを実装し、applicationやusecasesをimportしない。

## 永続モデル

- `ConversationCoordinator`: `character_id + chat_type + platform conversation id`
  から作るkeyごとに、active runを1件だけ持つmailbox。
- `AgentRun`: 受理したuser messageごとの実行。source chat idでidempotent。
- `AgentToolCall`: turnが要求したtoolと引数、結果、lease、continuationを保持する。

Run状態は`queued -> ready -> running -> waiting_for_tools -> ready`を基本とし、
終了は`completed / failed / cancelled`、遅延retryは`retry_wait`で表す。
Tool状態は`pending -> running -> succeeded / failed`で表す。

## 不変条件

1. 同一conversationで`ready/running/waiting_for_tools/retry_wait`になれるactive runは1件。
2. 外部I/O中にDB transactionを保持しない。claimとapplyは短いtransactionに分ける。
3. applyはclaim時のlease tokenが一致する場合だけ成功する。
4. transport eventの重複は正常系としてno-opにする。
5. tool結果はPostgreSQLに保存し、次turnは全terminal結果をまとめて受け取る。
6. send-message toolは単独callかつterminalとし、他toolとの曖昧なjoinを許さない。
7. reply chat、reply-ready Outbox、run状態変更は同一transactionでcommitする。
8. `app.error.detected`は観測専用で、制御フローへ再入しない。

## Leaseと復旧

RunとToolはclaim時にUUID lease tokenと期限を保存する。Worker停止後は30秒ごとのscanが
期限切れ`running`と期限到来`retry_wait`を再配送可能にする。再配送時にsequenceまたは
attempt countを進めるため、以前のイベントは状態を変更できない。

推論失敗は短い指数backoffで最大3回までretryする。turn上限到達時はrunをfailedにし、
mailbox内の次のqueued runをreadyへ昇格する。一般化したworkflow engineは作らず、
Agent固有の状態と遷移を明示したまま保つ。

## Cloudflareへの将来適合

将来Durable Objectsへ移す場合、`conversation_key`をobject id、coordinatorのadvanceを
object method、scheduled recoveryをalarmへ写せる。現在のcontractsとapplicationの
状態遷移はruntime非依存なので、presentation/transport/infrastructure adapterの差替えに
変更範囲を限定できる。
