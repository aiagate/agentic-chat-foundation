---
type: Memory Validation Policy
title: メモリの検証とエラー
description: memory document の現行エラー処理と、将来の検証ポリシーを区別して定義する。
tags: [memory, validation, errors, policy]
status: 現行実装と目標ポリシー
---

# 現行実装の振る舞い

- 単一 document の read は `MemoryMarkdownError` / `MemoryStoreError` を経由して `MemoryServiceError` へ畳み込まれる
- index scan は selected user scope のファイルを順に読むが、現行コードはファイル単位の診断集約よりも fail-fast に近い
- path scope と front matter `user_id` が不一致ならエラーにする

# 目標ポリシー

- top-level unknown field は warning または policy violation として扱う
- malformed file の diagnostics を集める
- another user の document を返さない

# 関連概念

- [共通 front matter](/common-frontmatter.md)
- [保存構造と実装参照](/storage-layout.md)
- [業務上の原則](../../product/ubiquitous-language/principles.md)
