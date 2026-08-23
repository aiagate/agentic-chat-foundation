---
okf_version: "0.1"
---

# ユースケース知識バンドル

このディレクトリは、agentic-chat-foundation の会話、関係育成、会話履歴整理に関する業務能力を表す OKF v0.1 バンドルである。
LLM や人間は、まずこのファイルを読み、必要な概念だけを開くこと。

## 読み方

### 目的と境界

- [プロジェクトの目的とアクター](/actors.md)
- [スコープ](/scope.md)
- [ハイレベルユースケース](/high-level-use-cases.md)

### 業務ユースケース

- [業務ユースケース一覧](/use-cases/)
- [メッセージを受け付ける](/use-cases/accept-incoming-message.md)
- [会話への応答を作成する](/use-cases/create-conversation-response.md)
- [応答結果を利用者へ届ける](/use-cases/deliver-conversation-result.md)
- [会話履歴を整理する](/use-cases/consolidate-conversation-history.md)

### 不変条件と結果

- [共通業務規則](/business-rules.md)
- [完了状態](/completion-states.md)
- [将来判断する事項](/future-decisions.md)

### 別Bounded Context

- [Discord公開議論](../discussion/index.md)

## 正本の扱い

このバンドルの業務上の記述がユースケースの正本である。実装クラス、データベース、
外部サービス、プロセス構成の説明は、必要に応じて別の技術リファレンスを参照する。
用語は[ユビキタス言語バンドル](../ubiquitous-language/index.md)で定義する。

## OKF 仕様

- [Open Knowledge Format v0.1 specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
- [Google Cloud: Open Knowledge Format のご紹介](https://cloud.google.com/blog/ja/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing)
