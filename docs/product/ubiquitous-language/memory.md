---
type: Domain Glossary
title: 外部情報と長期記憶
description: 外部情報、長期記憶、人物像、出来事、対象、関係、根拠、不確実性に関する業務用語を定義する。
tags: [domain-language, memory, external-information]
status: 業務上の正本
---

# 用語

| 用語 | 意味 |
|---|---|
| 外部情報 | 現在の応答を補うために外部情報源から取得する情報。取得しただけでは長期記憶にならない。 |
| 長期記憶 | 将来の対話に有用な意味を、会話履歴から整理して残したもの。 |
| 長期記憶の所有境界 | canonical User単位。チャネルやキャラクターをまたいで参照できるが、根拠chatの`character_id`は追跡可能にする。 |
| 人物像 | 利用者または対話相手について、比較的安定している特徴、嗜好、制約。 |
| 出来事 | ある期間の会話、状況、感情、結果をまとめた記憶。 |
| 対象 | 人物、物事、計画など、会話の中で継続的に参照されるもの。 |
| 対象間の関係 | 対象同士のつながり。キャラクターと利用者の好感度を表す関係状態とは異なる。 |
| 根拠 | 記憶の内容を支える会話と、その会話が観測された時点。 |
| 不確実性 | 記憶の内容を事実として確定できる度合い。 |
| 記憶整理 | 会話から有用な内容を選び、既存の長期記憶と比較し、作成・更新・統合・保留を判断すること。 |
| 保留 | 根拠や意味が十分でなく、長期記憶として確定しない状態。 |

# 関連概念

- [利用者と会話](/conversation.md)
- [業務上の原則](/principles.md)
- [対話相手との関係状態](/relationship.md)
- [Memory Markdown Schema](../../infrastructure/memory-markdown-schema/index.md)
- [UC-04 会話履歴を整理する](../application-use-cases/use-cases/consolidate-conversation-history.md)
