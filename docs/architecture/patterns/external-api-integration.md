# 外部API連携パターン

外部APIの都合をUseCaseやdomainへ漏らさず、契約とアダプタの境界で閉じ込める。

## 層の分離

| 層 | 役割 | 置き場 |
| :--- | :--- | :--- |
| `contracts/ports` | UseCaseが依存する契約 | `src/app/contracts/ports` |
| `infrastructure/services` | 外部SDK/APIのアダプタ | `src/app/infrastructure/services` |
| `usecases` | 契約を使う業務入口 | `src/app/usecases/conversation`、`memory` |

Domain固有の不変条件に閉じる型は`src/app/domain`へ置き、外部実装との境界は`contracts`へ置く。

## 具体例

### LLM provider

- 契約: `src/app/contracts/ports/ai_service.py`
- 実装: `gemini_service.py`、`gpt_service.py`
- テスト/開発用実装: `mock_ai_service.py`

`IAIService`は`GeneratedContent`を返し、チャネル送信や永続化を直接行わない。

### Web search

- 契約: `src/app/contracts/ports/web_search_service.py`
- tool実行: `src/app/infrastructure/services/tool_executor.py`
- 外部API実装: `src/app/infrastructure/services/ollama_web_search_service.py`

UC-02が同期的に呼び出し、結果を短期contextへ戻す。検索結果を長期memoryへ直接昇格しない。

### Memory

- 読み取り契約: `src/app/contracts/ports/memory_service.py`
- 書き込み契約: `src/app/contracts/ports/memory_write_service.py`
- 実装: `src/app/infrastructure/services/memory_service.py`、`memory_write_service.py`

長期memoryへの更新はUC-04へ集約する。会話中のtool実行状態を永続化しない。

## 置き場の判断

1. 境界契約なら`contracts/ports`
2. layerをまたぐDTOなら`contracts/messages`
3. 外部SDKを呼ぶ具象なら`infrastructure/services`
4. domainの不変条件に閉じる値・契約だけなら`domain`
