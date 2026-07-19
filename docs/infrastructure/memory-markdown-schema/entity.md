---
type: Memory Entity Schema
title: Entity memory
description: 正規化された対象と関係を表す Entity memory の保存規則と時間変化の扱いを定義する。
tags: [memory, entity, relationship, schema]
status: 現行実装の仕様
---

# 意味

Entity は normalized memory を表す。

# 保存規則

- path: `memory/entities/<user_scope>/<entity_id>.md`
- `properties` を Entity の属性値の正本として扱う
- 時間変化は`property_history`に旧値、`valid_to`、根拠chat IDを保持する
- `missing_attributes` で未解決情報を明示する

`referenced_in` は主に Timeline summary ID を指す。

# 関連概念

- [共通 front matter](/common-frontmatter.md)
- [保存構造と実装参照](/storage-layout.md)
- [対象と関係](../../product/ubiquitous-language/memory.md)
- [UC-04 会話履歴を整理する](../../product/application-use-cases/use-cases/consolidate-conversation-history.md)
