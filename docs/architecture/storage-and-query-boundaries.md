# Storage and Query Boundaries

この文書は、`Repository`、`Store`、`Query`、`Domain` の境界を定義する。
目的は、取得ロジック、永続化、短期保存、派生データ管理が混線するのを防ぐことである。

## 基本原則

- 取得の意思決定と永続化の実装は分離する。
- 派生データは source of truth ではなく projection として扱う。
- スキーマは実装コードではなく migration で管理する。
- 低レベル I/O と上位の検索ロジックを同じモジュールに置かない。

## `Repository`

`Repository` は永続化境界である。

### 責務

- DB への読み書き
- 永続化対象の保存、更新、削除
- トランザクション境界の外で使える入出力操作

### 禁止事項

- 検索順位の決定
- ビジネス上の選定ロジック
- UI や UseCase の事情による分岐
- HTML、Markdown、JSON のフォーマット生成

## `Store`

`Store` は短寿命または単純な保存領域である。

### 責務

- 一時的なコンテキストの保存
- ファイルパスやメモリ上のキーでの単純な読み書き
- 他層が必要とする中間状態の保持

### 禁止事項

- ドメイン上の判断
- 複雑な検索やランキング
- スキーマ管理
- 再構築ロジックの内包

## `Query`

`Query` は「読む」「探す」「選ぶ」「組み立てる」を担う。

### 責務

- 検索条件の解釈
- 複数ソースの集約
- ランキングやスコアリング
- 再推論や再構成のための入力整形
- projection からの派生ビュー構築

### 禁止事項

- 永続化の詳細を内包すること
- migration や ORM 定義を持つこと
- 一時保存の責務を持ち続けること

## `Domain`

`Domain` は意味のある概念のみを持つ。

### 置いてよいもの

- 集約
- 値オブジェクト
- ドメイン固有の抽象契約

### 置かないもの

- SQLModel/ORM の生実装
- ファイルシステムのパス計算
- API クライアント実装
- 純粋な I/O 補助関数

## 共有型の置き場

次のケースでは、境界をまたぐ小さな補助型を `contracts/messages` に置く。

- 複数レイヤーから参照される DTO
- イベント payload
- query や tool の入出力として共有される型

ただし、UseCase 固有で共有価値が低い型は `usecases` に残す。

## このリポジトリでの具体例

- `memory_index_documents` は main DB の projection として migration 管理する。
- `MemoryIndexRepository` は `src/app/infrastructure/repositories/memory_index_repository.py` に置き、スキーマ詳細を知らない永続化境界にする。
- `SQLAlchemyMemoryIndexQuery` は main DB projection から候補を取得し、`MemoryIndexSearch` は渡された候補のランキングに集中する。
- `MemorySleepQueryService` は `src/app/infrastructure/queries/memory_sleep_query_service.py` に置き、sleep 対象の選定に限定する。
- `InMemoryToolResultStore` と `InMemoryToolCallStore` は短期保存に限定する。
- `FilesystemMemoryStore` は `src/app/infrastructure/memory/store.py` に置き、Markdown memory の低レベル I/O に限定する。

## レビュー基準

新しい実装がどこに属するか迷ったら、次の順で判断する。

1. それは意味のある概念か。
2. 永続化なのか、一時保存なのか、取得ロジックなのか。
3. 生成物か、source of truth か、projection か。
4. どの層から参照されるか。
5. その配置で名前が誤認を生まないか。

## 運用ルール

- スキーマを実装ファイルに持ち込まない。
- `Repository` に検索計画を押し込まない。
- `Query` に永続化実装を押し込まない。
- `Store` を `Service` として誤分類しない。
- 派生データは migration と repository で管理し、必要なら query で再構成する。
