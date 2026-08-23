---
type: Completion States
title: 業務処理の完了状態
description: 応答と会話履歴整理が確定したときに成立する成功・失敗の状態を定義する。
tags: [product, outcomes, states]
status: 目標能力の定義
---

# 応答完了

応答結果が利用者へ届けられ、会話履歴へ反映されている。

# 応答不能

応答を作成または送達できないことが確定し、可能な範囲で利用者へ示され、会話履歴へ記録されている。

# 会話履歴整理完了

対象会話の評価、生成・更新すべき長期記憶、確定関係シグナルによる関係状態の更新が同じ処理単位で完了している。

# 会話履歴整理失敗

対象会話の長期記憶または関係状態更新を確定できず、その会話を未処理のまま再実行可能にしている。

# 関連概念

- [共通業務規則](/business-rules.md)
- [会話への応答を作成する](/use-cases/create-conversation-response.md)
- [応答結果を利用者へ届ける](/use-cases/deliver-conversation-result.md)
- [会話履歴を整理する](/use-cases/consolidate-conversation-history.md)
