---
type: Memory Profile Schema
title: Profile memory
description: 利用者または対話相手の比較的安定した属性を表す Profile memory の保存範囲を定義する。
tags: [memory, profile, schema]
status: 現行実装の仕様
---

# 意味

Profile は stable context を表す。event log ではなく、安定属性のみを持つ。

# Agent profile

- bundle path: `memory/profiles/agent/<character_id>/{AGENTS.md,SOUL.md,PERSONAL.md,MEMORY.md,RELATIONSHIP.yaml}`
- loader: [agent_profile_service.py](../../../src/app/infrastructure/services/agent_profile_service.py)
- immutable なアプリケーション設定であり、user-scoped memoryおよびmemory index projectionには含めない
- `AGENTS.md`、`SOUL.md`、`MEMORY.md`はfront matterを持たない
- `PERSONAL.md`を含むMarkdown人格定義はfront matterを持たない
- `RELATIONSHIP.yaml`は共通8段階に対応する応答コンテキスト候補だけを持つ。好感度の正本はSQLの関係集約であり、memory indexには含めない

# User profile

- path: `memory/profiles/users/<user_scope>.md`
- 共通memory front matterを持つ通常のmemory documentである

# 関連概念

- [共通 front matter](/common-frontmatter.md)
- [保存構造と実装参照](/storage-layout.md)
- [人物像](../../product/ubiquitous-language/memory.md)
