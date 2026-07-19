---
type: Memory Architecture Boundary
title: メモリ実装の責務境界とレビュー基準
description: メモリに関する共有型、境界契約、技術実装の配置とレビュー観点を定義する。
tags: [memory, architecture, boundaries, review]
status: 現行アーキテクチャの方針
---

# 使い分け

- `contracts/messages`: 共有 DTO / event / payload
- `contracts/ports`: 境界契約
- `infrastructure/memory`: parse / render / decay / path / I/O
- `infrastructure/services`: memory service と write adapter

# レビュー基準

- path が現行コードと一致しているか
- 境界契約を`contracts/ports`、共有DTOを`contracts/messages`に置いているか
- SQL raw chatだけをraw sourceと扱っているか
- current behavior と target behavior を区別しているか

# 関連概念

- [保存構造と実装参照](/storage-layout.md)
- [検証とエラー](/validation.md)
- [Storage and Query Boundaries](../../architecture/storage-and-query-boundaries.md)
