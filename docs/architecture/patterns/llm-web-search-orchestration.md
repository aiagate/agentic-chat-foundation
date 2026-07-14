# LLM Web Search Orchestration

`web_search`はUC-02「会話への応答を作成する」中の同期補助処理として扱う。

1. LLMが`web_search`のtool callを返す。
2. UC-02がtool catalogの制限を確認し、外部検索アダプタを呼び出す。
3. 検索結果を短期のtool contextへ変換し、同じ応答作成内で再推論する。
4. 再推論でtool callが残る場合、応答不能として結果を確定する。

検索結果は長期memoryへ直接保存しない。外部検索、tool実行、再推論のいずれかに失敗した
場合は即時失敗とし、AgentRun、lease、outbox、retry、recovery状態を生成しない。
