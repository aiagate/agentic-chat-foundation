# Memory Markdown Schema

この文書は、現在の filesystem-backed memory 実装で使っている Markdown front matter と
ファイル配置をまとめる。

## 目的

- memory の persisted schema を DTO から分離する
- user scope を明示して cross-user leakage を避ける
- parse / validation / I/O の失敗を `MemoryServiceError` 系に閉じる
- current behavior と target behavior を混ぜない

## 現行の保存構造

現行実装は `MEMORY_ROOT` または `MEMORY_AGENT_ROOT` から memory ルートを解決し、
`FilesystemMemoryStore` が path を組み立てる。

```text
memory/
  profiles/
    agent/
      <character_id>/
        AGENTS.md
        SOUL.md
        PERSONAL.md
        MEMORY.md
    users/
      <user_scope>.md
  timeline/
    <user_scope>/
      raw/
        YYYY/MM/YYYY-MM-DD_<role>-<id>.md
      daily/
        YYYY/MM/YYYY-MM-DD.md
      sections/
        YYYY/MM/YYYY-MM-DD_<slug>.md
  entities/
    <user_scope>/
      <entity_id>.md
```

`memory/profiles/agent/*.md` の flat layout は legacy fallback として残る。
新規の canonical path は `memory/profiles/agent/<character_id>/...` である。

## 現行の parser / writer

- parser と renderer は [src/app/infrastructure/memory/markdown.py](../../src/app/infrastructure/memory/markdown.py)
- path 解決と read/write は [src/app/infrastructure/memory/store.py](../../src/app/infrastructure/memory/store.py)
- memory context の組み立ては [src/app/infrastructure/services/memory_service.py](../../src/app/infrastructure/services/memory_service.py)
- raw Timeline の書き込みは [src/app/infrastructure/services/memory_write_service.py](../../src/app/infrastructure/services/memory_write_service.py)

現行 parser は、`schema_version`、`memory_type`、required field、timestamp の妥当性を検証する。
top-level unknown field の厳密な warning / error 分岐はまだ実装されていない。

## 共通 front matter

全 memory document に共通で必要な主な項目:

- `schema_version`: `1`
- `memory_type`: `profile` / `timeline` / `entity`
- `id`
- `memory_id`: agent runtime が `memory.read` に渡す stable key
- `created_at`
- `updated_at`
- `user_id`: user-scoped document では必須
- `tags`
- `importance`
- `confidence`
- `pinned`
- `metadata`
- `manifest_title`: 常駐 manifest に載せる短い表示名
- `manifest_summary`: 常駐 manifest に載せる 1 行概要

timestamp は timezone-aware ISO-8601 文字列を使う。

## Profile

Profile は stable context を表す。

### Agent profile

- bundle path: `memory/profiles/agent/<character_id>/{AGENTS.md,SOUL.md,PERSONAL.md,MEMORY.md}`
- loader: [src/app/infrastructure/services/agent_profile_service.py](../../src/app/infrastructure/services/agent_profile_service.py)

### User profile

- path: `memory/profiles/users/<user_scope>.md`

Profile は event log ではなく、安定属性のみを持つ。

## Timeline

Timeline は episodic memory である。

- raw Timeline は `memory.write_candidate` 由来の transitional path として現行実装に残っている
- daily summary は sleep/consolidation の結果として書く
- raw / section summary ともに、write 時点で `memory_id` / `manifest_title` / `manifest_summary` を front matter に持たせる
- `source_chat_ids` は SQL raw chat row の根拠
- `summary_of` は Markdown Timeline summary 同士の関係

raw Timeline Markdown は canonical raw log ではない。
SQL raw chat が source of truth である。

## Entity

Entity は normalized memory を表す。

- path: `memory/entities/<user_scope>/<entity_id>.md`
- `properties` を正とし、`attributes` は compatibility alias として扱う
- `missing_attributes` で未解決情報を明示する

`referenced_in` は主に Timeline summary ID を指す。

## 現行の検証とエラー

### 現行実装の振る舞い

- 単一 document の read は `MemoryMarkdownError` / `MemoryStoreError` を経由して `MemoryServiceError` へ畳み込まれる
- index scan は selected user scope のファイルを順に読むが、現行コードはファイル単位の診断集約よりも fail-fast に近い
- path scope と front matter `user_id` が不一致ならエラーにする

### 目標ポリシー

- top-level unknown field は warning または policy violation として扱う
- malformed file の diagnostics を集める
- another user の document を返さない

## 使い分け

- `contracts/messages`: 共有 DTO / event / payload
- `contracts/ports`: 境界契約
- `infrastructure/memory`: parse / render / decay / path / I/O
- `infrastructure/services`: memory service と write adapter

## レビュー基準

- path が現行コードと一致しているか
- `domain/interfaces` を境界契約置き場にしていないか
- raw Timeline を canonical source と誤認していないか
- current behavior と target behavior を区別しているか
