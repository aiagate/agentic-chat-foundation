# Agentic Chat Orchestration

Agentの複数step処理は、イベント同士を連鎖させるのではなく、PostgreSQL上の
`AgentRun`状態機械を`AgentRunCoordinator`が進める。

1. saved chatを`StartAgentRunHandler`が会話mailboxへ受理する。
2. `agent.run.wakeup`を受けた`AdvanceAgentRunHandler`が短期leaseをclaimする。
3. `AgentTurnRunner`がtransaction外でcontextを組み立てLLMを呼ぶ。
4. coordinatorがlease一致を確認してcontents/tool calls/次状態をatomicに反映する。
5. toolごとに`agent.tool.requested`を発行し、実行結果を`AgentToolCall`へ保存する。
6. 全toolがterminalになった時だけrunをreadyへ戻し、次のwakeupを発行する。

Redisは配送専用である。tool call、result、lock、retryはPostgreSQLのdurable rowへ置く。
`app.error.detected`は観測専用とし、制御フローのretry判断はrun状態が所有する。

設計制約と状態一覧は[Durable Agent Run](../durable-agent-run.md)を参照する。
