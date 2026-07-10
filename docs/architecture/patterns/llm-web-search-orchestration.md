# LLM Web Search Orchestration

`web_search`は通常のdurable toolとして扱う。

1. LLMが`ToolCall(tool_name="web_search")`を返す。
2. coordinatorがcatalogとcall上限を検証し、`AgentToolCall`とOutboxを保存する。
3. Workerが`agent.tool.requested`を受け、DB leaseをclaimしてexternal searchを実行する。
4. structured resultとprompt用rendered textをPostgreSQLへ保存する。
5. 同じturnの全tool完了後にrunをwakeupする。
6. 次turnはjoin済みtool resultsをまとめてcurrent inputへ入れる。

同じrequest eventの再配送はattempt countとstatusでno-opになる。実行中にprocessが停止した
場合はlease期限後にrecovery scanが再配送する。検索失敗もterminal resultとして保存し、
次turnが利用可能なcontextから回答を継続できる。
