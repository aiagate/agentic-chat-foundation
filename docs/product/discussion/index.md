---
type: Bounded Context Definition
title: Discord公開議論
description: 1対1会話core domainから独立した、Bot単位のDiscord公開議論を定義する。
tags: [product, discussion, discord, bounded-context]
status: 業務上の正本
---

# 境界

Discord公開議論は、複数の人間・Botが参加する公開チャンネル上の独立したBounded Contextである。
各Botは自身のキャラクター、ローカル履歴、非公開reflection、評価結果を持つ。
Bot間で共有する業務境界は、公開Discordチャンネルに現れるメッセージだけである。

このBounded Contextは、1対1会話core domainのcanonical `User`、短期会話履歴、長期記憶、
`CharacterRelationship`を参照・更新しない。

## アクター

- **Discord参加者**: 公開メッセージを投稿する人間または他Bot。
- **議論Bot**: 公開メッセージを観測し、発話または沈黙を決定する一つのキャラクター実行体。
- **Discord**: 公開メッセージの観測と発話結果の配送を担う外部チャネル。
- **時間**: 待機時間、アイドル時間、評価間隔、公開上限の判定を起動する。

## 業務ユースケース

| 業務ユースケース | 主な責務 |
| --- | --- |
| 公開メッセージを評価する | 新しい公開メッセージとローカル履歴から発話または沈黙を決める |
| 自発的な話題を評価する | チャネルがアイドル状態のとき、新しい話題を発話するか決める |
| 公開結果を届ける | 公開制限と新着メッセージによる置換を確認し、Discordへ届ける |

## 完了状態

評価結果は `silent`、`proposed`、`published`、`superseded`、`withheld`、`failed` のいずれかで確定する。
`proposed` は配送待ちの永続的な回復状態ではなく、公開前の一時的な業務結果である。
新しい公開メッセージが先に到着した場合、古い提案は`superseded`として確定し、新しい評価を開始する。

## 不変条件

- 各Botは他BotのDB、内部API、ロック、private memoryへ依存しない。
- recovered contextは履歴へ取り込むが、評価の起点にしない。
- 発話制限はBot自身のローカル観測だけで判定する。
- private reflectionを公開本文へ混入させない。
- 現在性のある情報源が入力されていない場合、ニュース、URL、引用、閲覧事実を創作しない。

## 技術対応

業務ユースケースの実装は`src/app/usecases/discussion/`に存在し、core domainの会話処理とは分離する。
このBounded Contextのアプリケーションフローとして扱う。DTOとPortは
`src/app/contracts/messages/discussion.py`および`src/app/contracts/ports/discussion.py`に置く。

詳細な実行・運用条件は[Autonomous Discord Discussion](../../infrastructure/discord-autonomous-discussion.md)を参照する。
