---
okf_version: "0.1"
---

# Memory Markdown Schema バンドル

このディレクトリは、filesystem-backed memory 実装で使う Markdown front matter、ファイル配置、
検証境界を表す OKF v0.1 バンドルである。これは技術リファレンスであり、記憶の業務上の意味は
[ユビキタス言語](../../product/ubiquitous-language/index.md)と[ユースケース知識バンドル](../../product/application-use-cases/index.md)を正本とする。

パス、項目名、解析エラーの扱いは実装とテストに追随して更新する。現行実装の振る舞いと目標ポリシーは、
同じファイル内でも見出しを分けて記述する。

## 読み方

- [保存構造と実装参照](/storage-layout.md)
- [共通 front matter](/common-frontmatter.md)
- [Profile](/profile.md)
- [Timeline](/timeline.md)
- [Entity](/entity.md)
- [検証とエラー](/validation.md)
- [責務の境界とレビュー基準](/boundaries.md)

## 関連する業務知識

- [外部情報と長期記憶](../../product/ubiquitous-language/memory.md)
- [UC-04 会話履歴を整理する](../../product/application-use-cases/use-cases/consolidate-conversation-history.md)
