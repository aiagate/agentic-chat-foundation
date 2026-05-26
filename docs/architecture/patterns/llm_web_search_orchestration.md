# LLM Web Search Orchestration

この文書は、`GeminiService` と `Ollama Web Search` を組み合わせる
ときの推奨アーキテクチャを定義する。

狙いは次の3点である。

- `IAIService` を純粋な推論境界として保つ
- 検索を短期受け渡しのワークフローとして扱う
- `memory_service` を長期記憶の責務に閉じ込める

## 背景

Gemini の function calling は、モデルが tool call を提案し、アプリ側
がその tool を実行して結果を再投入する構造である。
検索そのものはモデル内部の責務ではなく、アプリケーションが
オーケストレーションする外部処理として扱うのが自然である。

そのため、`GeminiService` の中に検索実行を埋め込まず、
`UseCase` と `Event` を介して接続する。

## Scope and boundaries

- `IAIService` は推論専用の境界であり、検索を実行しない。
- 検索結果は短期ワークフロー状態であり、`memory_service` には入れない。
- `retrieved context` は memory と chat history とは別の注入ブロックとして扱う。
- `search_session_id` は検索フロー単位の識別子であり、検索要求と結果を結び付ける。

## 設計方針

### 1. `IAIService` は推論結果として tool 要求を返す

`IAIService` の戻り値は、通常の生成結果だけでなく、
検索が必要な場合の tool request を表現できる必要がある。

このリポジトリでは `GeneratedContent.tool_use_request` のような
構造を持たせる案を採用する。

必要な性質は次のとおり。

- tool 呼び出し要否を構造化して表現できる
- ユーザー向けの中間メッセージを同梱できる
- 生成結果と tool request を同一レスポンスで扱える

### 2. 検索要求には `search_session_id` を付与する

検索イベントを発行する時点で `search_session_id` を採番し、以降の
イベントと短期ストアで同じ ID を使う。

この ID の役割は次のとおり。

- 検索要求と検索結果を結び付ける
- 一時的なコンテキストの参照キーにする
- 再推論時に検索結果を引くためのキーにする

### 3. 検索結果の受け渡しは短期ストアで行う

検索結果は `memory_service` に直接入れない。
代わりに短期受け渡し用の store を別に用意し、検索完了まで保持する。

`memory_service` に昇格させるのは、再利用価値が高く、長期記憶として
残す意味のある要約・抽出情報だけに限定する。

### 4. 検索結果は専用の retrieved context として注入する

検索結果は LLM にそのまま埋め込まず、`retrieved context` として
明示的に分離する。

理由は次のとおり。

- LLM に「検索結果である」と分かる形で渡せる
- system instruction や会話履歴と混ざりにくい
- 後で別ソースの検索結果を追加しやすい

## 推奨フロー

1. `GenerateContentHandler` が通常の履歴と memory context を集める
2. `IAIService` に推論を依頼する
3. 推論結果が tool request を含む場合、`search_requested` イベントを発行する
4. `search_requested` を worker が受けて Search UseCase を起動する
5. Search UseCase が Ollama Web Search を実行し、短期ストアに検索結果を保存する
6. Search UseCase が `search_completed` イベントを発行する
7. `search_completed` を worker が受けて再推論用 UseCase を起動する
8. 再推論用 UseCase が `search_session_id` から検索結果を読み出す
9. 検索結果を `retrieved context` として LLM に再投入する
10. 最終返信を発行する

## イベント責務

### `search_requested`

検索開始を通知するイベント。

payload に含めるもの。

- `search_session_id`
- `guild_id` / `channel_id` / `user_id`
- `chat_type`
- `prompt`
- `query`
- `source_request_id`
- `tool_name`
- `user_message`
- `max_results` があれば含める

### `search_completed`

検索結果が利用可能になったことを通知するイベント。

payload に含めるもの。

- `search_session_id`
- `chat_type`
- `user_id`
- `prompt`
- `result_count`
- `source_request_id`
- `tool_name`
- `guild_id` / `channel_id` があれば含める
- `status`

検索結果の本体は短期ストアから読む。

## `GeneratedContent` の扱い

`GeneratedContent` は最終出力の DTO であり続けるが、
検索分岐を表すために `tool_use_request` を持てるようにする。

想定イメージは次のようなものになる。

```python
@dataclass(frozen=True)
class SearchToolArguments:
    query: str
    max_results: int | None = None
    source_request_id: str | None = None


@dataclass(frozen=True)
class ToolUseRequest:
    search_session_id: str
    tool_name: Literal["web_search"]
    arguments: SearchToolArguments
    user_message: str


@dataclass(frozen=True)
class RetrievedContextItem:
    title: str | None = None
    url: str | None = None
    snippet: str
    content: str | None = None
    score: float | None = None


@dataclass(frozen=True)
class RetrievedContext:
    search_session_id: str
    query: str
    tool_name: Literal["web_search"]
    items: list[RetrievedContextItem]
    rendered_text: str


@dataclass(frozen=True)
class GeneratedContent:
    contents: list[str]
    tool_use_request: ToolUseRequest | None = None
```

ここでの `message` は、ユーザーに先に返す中間メッセージである。
たとえば「ちょっと検索してみます」が入る。

## `IAIService` の責務

`IAIService` は次のどちらかを返す。

- そのまま返信できる `GeneratedContent`
- tool request を含む `GeneratedContent`

`IAIService` は検索を実行しない。
検索実行は必ず UseCase 側で行う。

## `memory_service` の扱い

`memory_service` は長期記憶だけに使う。

適用対象。

- ユーザーの恒常的な嗜好
- 継続的に参照したい安定情報
- 検索結果を要約した知見

非対象。

- 1 回の検索フロー中だけ必要な検索結果
- 再推論までの中間状態

## 実装優先順位

1. `GeneratedContent.tool_use_request` を定義する
2. `search_session_id` を導入する
3. 短期ストア port を追加する
4. `search_requested` / `search_completed` を定義する
5. 検索結果を `retrieved context` として再投入する handler を追加する
6. 必要に応じて検索知見のみ `memory_service` に昇格する

## 関連ファイル

- `src/app/infrastructure/services/gemini_service.py`
- `src/app/contracts/ports/ai_service.py`
- `src/app/usecases/chat/generate_content.py`
- `docs/infrastructure/long_term_memory_target_architecture.md`
- `docs/infrastructure/memory_markdown_schema.md`
