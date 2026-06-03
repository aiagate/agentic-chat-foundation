# Service Role Guidelines

この文書は、`Service` という名前を持つ実装の責務を定義する。
目的は、`Service` が何でも屋になることを防ぎ、`Query`、`Repository`、`Store` との境界を明確にすることである。

## 基本原則

- `Service` は振る舞いの単位であり、型の寄せ集めではない。
- `Service` は責務を 1 つに保つ。
- `Service` は外部依存やオーケストレーションを持つときに使う。
- `Service` の中にスキーマ定義、SQL の生文字列、ファイルフォーマットの詳細を埋め込まない。
- `Service` と名乗るなら、呼び出し側から見て役割が名前だけで分かること。

## `Service` に置いてよいもの

- 外部 API アダプタ
- AI 推論アダプタ
- 複数の取得/更新処理をまとめるアプリケーション寄りのオーケストレーション
- ドメイン概念を実装するが、リポジトリではない処理

## `Service` に置かないもの

- 単純な in-memory 保存
- ファイルパスの生成だけを行う処理
- Markdown や JSON の純粋な変換関数
- DB スキーマ定義
- クエリの選定ロジック
- ただの補助関数群

## 命名基準

- `*Service` は、少なくとも 1 つの明確な外部境界またはアプリケーション振る舞いを持つこと。
- `*QueryService` は、取得・集約・選定・再構成を主責務とする。
- `*Repository` は、永続化の入出力を担う。
- `*Store` は、短寿命または単純な保存領域を担う。
- `*Helper` や `*Util` は、増殖しやすいので原則避ける。

## レビュー基準

新しい `Service` を追加する前に、次を確認する。

- この処理は本当に `Service` でなければならないか。
- `Query`、`Repository`、`Store` に分解できないか。
- 呼び出し側が責務を誤認しないか。
- 既存の `Service` に責務を足して肥大化させていないか。

## このリポジトリでの具体例

- `GptService` と `GeminiService` は、外部 AI 境界の差し替え実装なので `Service` として妥当である。
- `OllamaWebSearchService` は、外部 web search API のアダプタなので `Service` として妥当である。
- `FilesystemMemoryService` は、`src/app/infrastructure/memory/store.py` と検索インデックスを束ねる取得オーケストレーションなので `Service` として妥当である。
- `FilesystemAgentProfileService` は、プロファイル束の読み込みサービスなので `Service` として妥当である。
- `MemoryConsolidationService` は、抽出結果の反映というオーケストレーションを持つため `Service` として妥当である。
- `GenericToolExecutor` は、tool ごとの実行先をまとめるアダプタなので `Service` として妥当である。
- `InMemoryRetrievedContextStore` は `Service` ではなく `Store` とする。
- `MemorySleepQueryService` は `Service` ではなく `Query` 側に置く。
- `memory/store.py` や `markdown.py` のような低レベル I/O と変換関数は `Service` にしない。

## 反例

- `Service` に `schema` と `repository` と `query` が同居している。
- `Service` という名前で、実態は純粋関数と定数だけである。
- `Service` が「読み取り」「更新」「検索」「整形」を全部抱えている。

## 運用ルール

1. 新規実装を置く前に責務を一文で説明できることを確認する。
2. 説明できない場合は、まず境界を分解する。
3. 分解後もなお `Service` が必要な場合だけ、`Service` として配置する。
4. `Service` の責務が 2 つ以上見えたら、原則として分割を検討する。
