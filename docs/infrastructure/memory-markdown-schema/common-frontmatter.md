---
type: Memory Document Schema
title: 共通 front matter
description: memory document が共有する front matter 項目、必須項目、timestamp の形式を定義する。
tags: [memory, schema, frontmatter]
status: 現行実装の仕様
---

# 共通項目

user profile、Timeline、Entityで共通に利用する主な項目（すべてが必須ではない）:

- `schema_version`: `1`
- `memory_type`: `profile` / `timeline` / `entity`
- `id`
- `memory_id`: 応答作成中のmemory詳細読み取りに使う stable key。未指定時は`memory_type`と`id`などからformatterが補う
- `created_at`
- `updated_at`
- `user_id`: user-scoped document では必須
- `tags`
- `importance`
- `confidence`
- `pinned`
- `metadata`
- `manifest_title`: 常駐 manifest に載せる短い表示名。未指定時はdocument種別・本文などからformatterが補う
- `manifest_summary`: 常駐 manifest に載せる 1 行概要。未指定時はdocument種別・本文などからformatterが補う

# 必須検証

parserが必須として検証するのは、共通の`schema_version`/`memory_type`/`id`/timestampと、document種別ごとの
required fieldである。`tags`、`importance`、`confidence`、`pinned`、`metadata`、manifest項目はdocumentにより省略できる。

timestamp は timezone-aware ISO-8601 文字列を使う。

`memory/profiles/agent/<character_id>/` は immutable なagent設定であり、
memory documentではないため、この共通schemaおよびmemory index projectionの対象外とする。

# 関連概念

- [保存構造と実装参照](/storage-layout.md)
- [Profile](/profile.md)
- [Timeline](/timeline.md)
- [Entity](/entity.md)
- [検証とエラー](/validation.md)
