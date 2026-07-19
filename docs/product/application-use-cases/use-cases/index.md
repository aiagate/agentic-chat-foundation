# 業務ユースケース一覧

このディレクトリには、業務ユースケースを1概念1ファイルで格納する。
各ファイルの YAML フロントマターに `type: Business Use Case` を持たせ、本文に目的、アクター、
起点、条件、基本フロー、代替・例外フロー、事後条件、最低保証を記述する。

## 会話の流れ

1. [メッセージを受け付ける](accept-incoming-message.md)
2. [会話への応答を作成する](create-conversation-response.md)
3. [応答結果を利用者へ届ける](deliver-conversation-result.md)

## 定期的な会話履歴整理

- [会話履歴を整理する](consolidate-conversation-history.md)
