# Architecture Overview

この文書は、現在の業務ユースケースに沿った実行構成を示す。設計の正本は
[アクター別ユースケースと記述](../product/application-use-cases.md) と
[一括改修計画](application-rebuild-plan.md) である。

## 依存方向

```text
presentation -> usecases -> application -> contracts/domain
infrastructure -> contracts/domain
```

- `presentation`: Discord、LINE、定期実行の入口とチャネル送信アダプタ。
- `usecases`: 外部要求ごとのCommand/Query入口。1 module 1 Handler。
- `application`: 応答作成や記憶整理で共有する業務補助サービス。
- `contracts/ports`: AI、tool、会話履歴、記憶、送信などの境界。
- `contracts/messages`: layerをまたぐ会話・AI・memory DTO。
- `domain`: 会話と記憶に固有の値、repository/query契約。
- `infrastructure`: PostgreSQL、ORM、AI provider、memory、外部検索の実装。

UseCase同士は呼び出さない。複数のUseCaseから再利用する処理は
`application` または責務を表すinfrastructure serviceへ切り出す。

## プロセス

- `bot`: Discord DMの受信、UC-01〜UC-03、Discordへの返信。
- `line`: LINE webhookの受信、UC-01〜UC-03、LINEへの返信。
- `worker`: UC-04（周期的な長期記憶整理）の起動だけを担当する。
- `migrate`: Alembic migration。
- `postgres`: raw chat logとmemory projectionの正本。

会話処理は受信したプロセス内で、次の論理順に完了する。

```text
UC-01 AcceptIncomingMessage
  -> UC-02 CreateConversationResponse
  -> UC-03 DeliverConversationResult
```

Redis、transactional outbox、AgentRun、lease、retry、recoveryは会話フローの前提にしない。

## 会話フロー

1. チャネルアダプタが外部メッセージを`IncomingMessage`へ変換する。
2. UC-01がuserメッセージをraw chat logへ保存し、`AcceptedMessage`を返す。
3. UC-02が直近履歴、profile、episode、entity/relationshipを読み、必要な外部検索を同期実行して応答を作る。
4. UC-03が元のチャネルへ送信し、送信成功後にassistantメッセージをraw chat logへ保存する。
5. どの段階でも失敗は即時結果として確定し、自動再実行用の状態を生成しない。

外部メッセージIDは受信時に保存し、同じチャネル・IDの再受付を一件に制限する。
チャネル固有の識別子は単一の会話メッセージモデルのメタデータとして保持し、
Discord/LINE用の継承集約やTPH別名は持たない。

## 長期記憶

raw chat logはuser・assistant双方のメッセージを保持する。UC-04は未整理のraw logを
周期的に読み取り、次の3種類を更新する。

- profile: 利用者・エージェントの安定した属性。
- episode: 期間内の出来事を圧縮した要約。
- entity/relationship: 正規化された事実と関係。

memory documentの変更に対応するprojectionだけを更新し、全件rebuild、repair、backup、
startup時の再構築は行わない。整理に失敗した回は失敗として終了する。

## ユースケースとポート

| UseCase | 主なポート |
| --- | --- |
| `AcceptIncomingMessage` | `ConversationHistory` |
| `CreateConversationResponse` | `ConversationContext`、`ResponseGenerator`、同期`ToolExecutor` |
| `DeliverConversationResult` | `ConversationResultSender`、assistant履歴書き込み |
| `OrganizeLongTermMemory` | raw chat query、`MemoryConsolidator`、memory store/projection |

チャネル、AI provider、DB、ファイル形式はUseCaseから直接参照しない。

## 対象外

組織・team・membership管理、管理API、グループ会話、メディア入力、自発的通知、
配送保証、障害回復、永続的な処理待ちはこのアプリケーションの対象外である。
