# 長期記憶 3 層 Markdown リファクタ計画

この文書は、長期記憶リファクタの履歴と棚卸しを残すための計画書である。
現在の正本方針は `docs/infrastructure/long_term_memory_target_architecture.md`
と `docs/infrastructure/memory_markdown_schema.md` を優先する。

## 目的

長期記憶システムを、読みやすく機械でも書き込みやすい 3 層 Markdown アーキテクチャとして実装する。

- Profile: 安定したユーザー属性とエージェント属性
- Timeline: SQL raw chat log から作る時系列のエピソード要約
- Entity: 具体的な対象、仕様、未解決プレースホルダー

presentation コードは薄く保つ。Bot、LINE、API、worker の各 entry point は memory storage を直接扱わない。Chat 生成は引き続き `GenerateContentHandler` を通し、その依存先は `IMemoryService` のみにする。

## 現状

このリポジトリには、すでに app-owned の memory 境界がある。

- `src/app/contracts/ports/memory_service.py`
- `src/app/contracts/messages/memory_context.py`
- `src/app/infrastructure/services/memory_service.py`
- `src/app/usecases/chat/generate_content.py`
- `docs/infrastructure/memory_markdown_schema.md`

現状の棚卸し:

- raw chat の正本は SQL とする。raw Timeline Markdown は legacy/manual/暫定データであり、chat raw の正本ではない。
- Timeline Markdown は、SQL raw chat log から作る日次・周期的な抽象要約を主対象にする。
- sleep/consolidation には deterministic summary / deterministic consolidation の性格が残っており、目標の LLM 意味圧縮へ移行中である。
- 検索は SQLite metadata と deterministic search を中心にした段階で、`sqlite-vec` semantic retrieval は目標状態である。
- sleep 後の Markdown 更新を index 更新と retrieval に完全接続する経路は未完了である。
- `source_chat_ids` は SQL raw chat row の根拠、`summary_of` は Markdown Timeline summary 同士の再要約・継承関係として使い分ける。
- Entity と Timeline のリンクは `referenced_in` と `source_chat_ids` の役割分担を保ちながら整理する。
- `MEMORY_AGENT_ROOT` は legacy 環境変数名として残っている。

## アーキテクチャ境界

次の境界を守る。

- `contracts/messages`: use case が受け取る DTO
- `contracts/ports`: `IMemoryService` と `Result` ベースのエラー契約
- `infrastructure/services`: Markdown パース、file I/O、indexing、ranking、decay、context assembly、sleep/consolidation
- `usecases/chat`: `IMemoryService` を呼ぶだけにし、memory search や ranking を持たない
- `presentation`: memory に直接触らない

Profile、Timeline、Entity は、現時点では domain aggregate にしない。これは storage/application memory の概念として扱う。強い業務不変条件が増えたときに domain 化を再検討する。

## 変更対象

### Documentation

- `docs/infrastructure/memory_markdown_schema.md` を更新する
- Profile、Timeline、Entity の front matter を定義する
- search 対象フィールドを定義する
- context frame の順序を定義する
- sleep/consolidation の状態を定義する
- decay の入力と計算方針を定義する
- Entity の path ルールを確定する

### Contracts

- `src/app/contracts/messages/memory_context.py` を更新する
- `MemorySearchHit`
- `MemoryContextFrame`
- `MemoryFrameSection`
- `MemorySource`
  などを追加する
- persisted front matter schema と search result metadata は分ける

- `src/app/contracts/ports/memory_service.py` は初期段階では大きく変えない
- `retrieve()` を主入口として維持しつつ、組み立て済み context を返す方向に進化させる
- `Result[..., MemoryServiceError]` は維持する

### Infrastructure

`src/app/infrastructure/services/memory_service.py` を次の内部モジュールへ分割する。

- `memory_markdown.py`: front matter の parse/render
- `memory_store.py`: filesystem path 解決と read/write
- `memory_index.py`: `search_memory_index`
- `memory_context_assembler.py`: `assemble_context_frame`
- `memory_decay.py`: score decay と access metadata
- `memory_service.py`: `FilesystemMemoryService` adapter

`FilesystemMemoryService` は DI される実装として維持する。

### Use Case

- `src/app/usecases/chat/generate_content.py` を更新する
- `_build_memory_instruction()` は削除または縮小する
- 組み立て済み memory context を `MemoryContextPack` から AI service に渡す
- memory failure の処理は `Result` チェックのままにする

### Configuration

- `.env.example` を更新する
- `MEMORY_ROOT` を優先する
- 互換性のため `MEMORY_AGENT_ROOT` は fallback として残す

## 目標ストレージ構成

user ごとにデータが衝突しないよう、user-scoped storage を使う。

```text
memory/
  profiles/
    agent.md
    users/
      <user_id>.md
  timeline/
    <user_id>/
      daily/
        YYYY/
          MM/
            YYYY-MM-DD.md
  entities/
    <user_id>/
      <entity_id>.md
  catalog.json
```

`catalog.json` は最初の実装では optional とする。無ければ Markdown を scan して index を作る。

raw Timeline Markdown の旧パス
`memory/timeline/<user_id>/raw/YYYY/MM/YYYY-MM-DD_<role>-<id>.md` は、
legacy 互換、手動投入、または移行中の暫定データに限る。自動 writer は
SQL raw chat log を正本として扱い、Markdown には抽象化済み Timeline summary
を書き込む。

## 実装フェーズ

### Phase 1: Schema First

deliverables:

- `docs/infrastructure/memory_markdown_schema.md` の再構成
- versioned front matter の定義
- path convention の確定
- context frame ルールの明文化
- sleep/consolidation 状態の明文化

acceptance criteria:

- docs がコード変更前に target shape を正確に示している
- Entity path convention が実装予定と一致している
- agent と user の Profile 分離が明確である

### Phase 2: DTO と Contract

deliverables:

- `memory_context.py` の拡張
- context frame DTO の追加
- search hit DTO の追加
- `IMemoryService.retrieve()` を外部 read の主入口として維持

acceptance criteria:

- use case が search internals を知らずに context を受け取れる
- DTO が pyright strict を通る
- 既存テストの Result ベースの振る舞いを壊さない

### Phase 3: Markdown Parser と Store

deliverables:

- `memory_markdown.py` に front matter parse を切り出す
- `memory_store.py` に path と filesystem 操作を切り出す
- parse/read/write failure を `MemoryServiceError` に変換する
- schema version validation を追加する

acceptance criteria:

- 壊れた Markdown は `Err(MemoryServiceError)` になる
- Profile、Timeline、Entity は round-trip できる
- `FilesystemMemoryService` の公開振る舞いは DI 可能なまま残る

### Phase 4: Search Index

deliverables:

- `memory_index.py` を追加する
- `search_memory_index(query, filters)` を実装する
- Profile、Timeline、Entity の metadata/body を layer-specific に検索する
- memory type、tags、date range、status、unresolved state、user id を filter できるようにする
- 依存追加なしの simple scoring を導入する

acceptance criteria:

- query が retrieved memory に影響する
- Entity alias と properties が検索可能である
- unresolved high-importance Entity を boost できる
- 他ユーザーの記憶は返らない

### Phase 5: Context Frame Assembly

deliverables:

- `memory_context_assembler.py` を追加する
- Primary、Functional、Peripheral を実装する
- `## Source: <path>` の source header を付ける
- size budget を持たせる
- 組み立て済み context を `MemoryContextPack` へ返す

acceptance criteria:

- Profile が安定文脈として含まれる
- 直接一致した Entity が Primary または Functional に現れる
- Timeline 要約が Peripheral または補助文脈に入る
- `GenerateContentHandler` が ranking や assembly を持たない

### Phase 6: Entity と Timeline Linking

deliverables:

- unresolved Entity を扱えるようにする
- `missing_attributes`、`properties`、`referenced_in`、`last_updated` を追加する
- consolidation 時に Timeline の `entities` / `entity_ids` を埋める
- Entity の deterministic merge/update を実装する

acceptance criteria:

- 不明属性を明示できる
- Timeline summary が Entity ID を参照できる
- Entity file が参照先 Timeline summary を持つ

### Phase 7: Sleep、Consolidation、Decay

deliverables:

- `memory_decay.py` を追加する
- decay score を計算する
- SQL raw chat log から daily Timeline summary への consolidation を追加する
- low-importance archival を追加する
- access metadata を更新する

acceptance criteria:

- decay が deterministic で unit test 可能
- SQL raw logs を daily Timeline document に要約できる
- 低重要度の古い Timeline 詳細を archive/compress できる
- pinned や高重要度の記憶を誤って消さない

### Phase 8: Generate Content Integration

deliverables:

- `GenerateContentHandler` の更新
- 組み立て済み context frame を `system_instruction` として利用
- user と assistant の logging を生成後に維持
- エラーの振る舞いを明示する

acceptance criteria:

- AI call が assembled context を受け取る
- memory retrieval failure は use case error になる
- memory persistence failure も use case error になる
- presentation code は変わらない

### Phase 9: Verification と Cleanup

deliverables:

- parser、store、index、assembler、decay、generate content integration の focused test を追加する
- 既存の memory service tests を更新する
- obsolete behavior を安全に削除する
- legacy environment fallback は明文化された範囲だけに残す

acceptance criteria:

- `uv run --frozen ruff format --check .`
- `uv run --frozen ruff check .`
- `uv run --frozen pyright`
- `uv run --frozen pytest -o addopts='' tests/infrastructure/services tests/usecases/chat/test_generate_content.py`
- `uv run --frozen pytest`

## サブエージェント分担

サブエージェントは search engine ではなく高負荷の実行者として扱う。分担は Profile/Timeline/Entity の layer 単位ではなく、境界ごとに切る。layer ごとに分けると front matter、user scope、Result error、search の責務が重複して不整合になる。

各サブエージェントは、担当ファイル、実行した test、残リスクを返すこと。

### Agent A: Schema / Documentation

scope:

- `docs/infrastructure/memory_markdown_schema.md`
- 必要なら `docs/plan/long_term_memory_3_layer_markdown_plan.md`

responsibilities:

- 3 層の意味を確定する
- Markdown/YAML front matter を定義する
- path convention を定義する
- required / optional field を定義する
- malformed file の扱いを定義する
- search-indexed fields を定義する
- context-frame assembly rules を定義する
- sleep/consolidation states を定義する
- Entity file path の不一致を解消する

output:

- 更新済み schema 文書
- 実装可能な acceptance criteria
- 未決事項があれば明記

dependencies:

- 最初に着手する
- 他の agent はこの schema を contract として扱う

### Agent B: Contract / Use Case Boundary

scope:

- `src/app/contracts/messages/memory_context.py`
- `src/app/contracts/ports/memory_service.py`
- `src/app/usecases/chat/generate_content.py`
- `tests/usecases/chat/test_generate_content.py`

responsibilities:

- Markdown storage details を use case に漏らさない DTO を設計する
- `IMemoryService` を Result ベースに保つ
- assembled context の渡し方を定義する
- presentation と Cog から memory persistence を遠ざける
- use case から ranking / assembly を外す

output:

- 安定した memory retrieval contract
- 薄い generate-content integration
- 更新済み use case tests

dependencies:

- Agent A と並行して DTO の叩き台は作れる
- Agent A が schema 用語と frame shape を固めた後に最終化する

### Agent C: Filesystem Adapter / Markdown Infrastructure

scope:

- `src/app/infrastructure/services/memory_markdown.py`
- `src/app/infrastructure/services/memory_store.py`
- `src/app/infrastructure/services/memory_service.py`
- `.env.example`
- `tests/infrastructure/services/test_memory_service.py`

responsibilities:

- `memory_service.py` から Markdown parse と filesystem store を分離する
- schema version validation を実装する
- front matter type validation を実装する
- read/write/parse failure を `MemoryServiceError` に変換する
- user-scoped path を実装する
- `MEMORY_ROOT` 優先と `MEMORY_AGENT_ROOT` fallback を実装する
- `FilesystemMemoryService` を DI adapter として維持する

output:

- round-trip 可能な Markdown persistence
- valid / empty / Unicode / malformed に対する parser/store tests
- infrastructure 外に storage 依存を出さない

dependencies:

- Agent A の schema に依存する
- Agent D と E に document loading API を提供する

### Agent D: Index / Assembly / Decay

scope:

- `src/app/infrastructure/services/memory_index.py`
- `src/app/infrastructure/services/memory_context_assembler.py`
- `src/app/infrastructure/services/memory_decay.py`
- `src/app/infrastructure/services/memory_service.py`
- `tests/infrastructure/services/test_memory_index.py`
- `tests/infrastructure/services/test_memory_context_assembler.py`
- `tests/infrastructure/services/test_memory_decay.py`

responsibilities:

- `search_memory_index` を実装する
- metadata と body の keyword scoring を実装する
- type、tags、date、status、unresolved state、user で filter する
- deterministic decay scoring を実装する
- `assemble_context_frame` を実装する
- Primary、Functional、Peripheral を組む
- source headers を付ける
- size budget を守る

output:

- score と matched terms を持つ search result
- `GenerateContentHandler` に渡せる assembled context frame
- ranking、decay、source attribution、budget の deterministic tests

dependencies:

- Agent C の store API に依存する
- Agent B の DTO shape と合わせる

### Agent E: Consolidation / Test / Review

scope:

- `src/app/infrastructure/services/memory_service.py`
- `src/app/infrastructure/services/memory_decay.py`
- scheduled execution 用の worker integration files
- `tests/infrastructure/services/test_memory_sleep.py`
- 影響を受ける既存 tests

responsibilities:

- SQL raw chat log から daily Timeline への consolidation を実装する
- consolidation states を追加する
- duplicate suppression を追加する
- unresolved Entity linking と confidence / update rules を追加する
- low-importance archival/compression を追加する
- focused tests を実行する
- final lint / type / full pytest を実行する
- docs と implementation の一致をレビューする
- presentation が memory storage に直接触れていないことを確認する

output:

- deterministic sleep/consolidation functions
- regression tests
- residual risk を含む最終レビュー報告

dependencies:

- Agent A、C、D に依存する
- 最終レビューは全 agent 完了後
- worker scheduling は明示依頼が無い限り範囲外

## 並行化方針

波ごとに進める。

1. Wave 1: Agent A が schema/docs を固める
2. Wave 2: Agent B が DTO/use case contract を詰める
3. Wave 3: Agent C が parser/store を実装する
4. Wave 4: Agent D が index/assembler/decay を実装する
5. Wave 5: Agent E が consolidation と最終検証を行う

安全な並行作業:

- Agent B は infrastructure 完成前でも mocked `MemoryContextPack` で進められる
- Agent D は Agent C の filesystem 詳細が固まる前に in-memory fixture で始められる
- Agent E は Agent A が consolidation states を定義した後なら sleep test fixture を作れるが、最終 linking は Agent D の index shape が固まるまで待つ

## 検証コマンド

`uv` のみを使う。

```powershell
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen pyright
uv run --frozen pytest -o addopts='' tests/infrastructure/services tests/usecases/chat/test_generate_content.py
uv run --frozen pytest
```

focused pytest が coverage gate だけで止まる場合は、開発中は `-o addopts=''` を使い、最終確認では full suite を通す。
