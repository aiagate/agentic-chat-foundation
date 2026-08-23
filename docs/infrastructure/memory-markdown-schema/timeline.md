---
type: Memory Timeline Schema
title: Timeline memory
description: 会話期間の経験をまとめる section summary と、その根拠を表す Timeline memory の保存規則を定義する。
tags: [memory, timeline, episodic-memory, schema]
status: 現行実装の仕様
---

# 意味

Timeline は episodic memory である。

# 保存規則

- Timeline documentはUC-04が生成するsection summaryだけである
- section summaryはwrite時点で `memory_id` / `manifest_title` / `manifest_summary` を持つが、profile/entityはformatterのfallbackに依存できる
- `source_chat_ids` は各 section に実際に含めた SQL raw chat row の根拠
- 複数 section を生成する場合、同じ raw chat ID を複数 section に割り当てない
- `summary_of` は Markdown Timeline summary 同士の関係

SQL raw chatが唯一のraw source of truthである。

# 関連概念

- [共通 front matter](/common-frontmatter.md)
- [保存構造と実装参照](/storage-layout.md)
- [出来事](../../product/ubiquitous-language/memory.md)
- [UC-04 会話履歴を整理する](../../product/application-use-cases/use-cases/consolidate-conversation-history.md)
