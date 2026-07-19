---
type: Memory Storage Layout
title: メモリの保存構造と実装参照
description: filesystem-backed memory の canonical path、保存構造、parser・writer の実装参照を定義する。
tags: [memory, storage, filesystem, implementation]
status: 現行実装の仕様
---

# 目的

- memory の persisted schema を DTO から分離する
- user scope を明示して cross-user leakage を避ける
- parse / validation / I/O の失敗を `MemoryServiceError` 系に閉じる
- current behavior と target behavior を混ぜない

# 現行の保存構造

現行実装は `MEMORY_ROOT` から memory ルートを解決し、
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
      sections/
        YYYY/MM/YYYY-MM-DD_<slug>.md
  entities/
    <user_scope>/
      <entity_id>.md
```

agent profileのcanonical pathは `memory/profiles/agent/<character_id>/...` だけである。
flat layout `memory/profiles/agent/*.md` のfallback readerは現行実装にない。
agent profileはimmutableな設定として専用parserで読み、通常memoryのparser、検証、検索projectionには渡さない。
Timelineはsection summaryだけを書き、raw Timelineとdaily summaryは生成しない。

# 現行の parser / writer

- parser と renderer は [markdown.py](../../../src/app/infrastructure/memory/markdown.py)
- agent profileのoptional metadata parserは [agent_profile_markdown.py](../../../src/app/infrastructure/memory/agent_profile_markdown.py)
- path 解決と read/write は [store.py](../../../src/app/infrastructure/memory/store.py)
- memory context の組み立ては [memory_service.py](../../../src/app/infrastructure/services/memory_service.py)
- profile、episode、対象間の関係を含むentityの整理・反映は[UC-04](../../product/application-use-cases/use-cases/consolidate-conversation-history.md)の責務である。キャラクターと利用者の好感度はMarkdownへ保存しない。

# 関連概念

- [共通 front matter](/common-frontmatter.md)
- [Profile](/profile.md)
- [Timeline](/timeline.md)
- [Entity](/entity.md)
