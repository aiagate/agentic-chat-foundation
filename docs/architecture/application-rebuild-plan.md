# ユースケース準拠の一括改修計画

## 1. 目的

`docs/product/application-use-cases.md` で定義した4つの業務ユースケースを、
過度な耐障害性や実装上の都合に引きずられない、明朗なアプリケーション構造へ一括で
実装するための計画である。

本計画は段階リリースや互換層を設ける計画ではない。1回の変更セットで、対象外の機能を
削除し、ユースケース、契約、永続化、入口、テストを同時に整合させる。

## 2. 完成時の能力

実装後に保証する業務上の入口は次の4つだけとする。

| ID | アプリケーション入口 | 起点 | 結果 |
|---|---|---|---|
| UC-01 | `AcceptIncomingMessage` | チャネルからのテキスト入力 | 利用者・会話に紐づく履歴と応答対象 |
| UC-02 | `CreateConversationResponse` | UC-01の受付結果 | 応答または応答不能の論理結果 |
| UC-03 | `DeliverConversationResult` | UC-02の論理結果 | 元のチャネルへの送信結果 |
| UC-04 | `OrganizeLongTermMemory` | 定期的な時間契機 | profile / episode / entity-relationship の更新結果 |

チャネル差異、AI provider、外部検索、履歴・記憶ストアは、上記入口から利用する補助境界で
あり、追加の業務ユースケースにはしない。

## 3. 目標構造

### 3.1 UseCase

`src/app/usecases` 直下に、4つのUseCaseと入力・結果DTOを置く。

- `conversation/accept_incoming_message.py`
- `conversation/create_conversation_response.py`
- `conversation/deliver_conversation_result.py`
- `memory/organize_long_term_memory.py`（`OrganizeLongTermMemory`）

各UseCaseは外部要求を受け、1つの業務結果を返す。チャネル別の変換、LLM呼び出し、検索、
記憶ファイルの形式変換はUseCaseに埋め込まず、契約で表したポートの実装へ委譲する。

### 3.2 業務境界の契約

次の契約を `src/app/contracts/ports` と `src/app/contracts/messages` に整理する。

- `IncomingMessage` / `AcceptedMessage` / `ConversationResult` / `DeliveryResult`
- `ConversationHistory`（raw履歴の読み書き）
- `ConversationContext`（履歴・profile・episode・entity/relationshipの読み取り）
- `ResponseGenerator`（必要なら外部情報を取得して応答を作成）
- `ConversationResultSender`（チャネル非依存の送信）
- `MemoryConsolidator`（3種類の長期記憶を一度に整理）

受信、応答作成、結果配信は論理境界として分離するが、Discord/LINEでは同一リクエスト内で
直列実行する。配送保証、lease、outbox、retry、recoveryを契約の前提にしない。

### 3.3 ドメインと永続化

- 会話はチャネル種別を持つ単一の会話モデルとし、Discord/LINEの継承名やTPHを廃止する。
- 外部チャネル識別子は `ConversationParticipant` の一部として保存し、内部利用者IDと混同しない。
- raw履歴は一つの履歴リポジトリを正本とする。
- 長期記憶は profile、episode、entity/relationship の3種類を明示した記憶モデルとして保存する。
- AgentRun、lease、attempt、wake sequence、outboxなど、耐障害性専用の状態は削除する。

既存DBを段階的に温存する移行は行わない。新しいモデルに合わせたmigrationを追加し、不要な
テーブル・列・インデックスを同じ変更セットで削除する。

## 4. 一括変更の実行順序

順序は依存関係を安全に保つための作業順であり、リリースフェーズではない。

1. 4 UseCaseの入力・結果、会話・記憶モデル、ポート契約を確定する。
2. 会話履歴と長期記憶のリポジトリ、AI応答生成、外部検索、チャネル送信アダプタを新契約へ合わせる。
3. UC-01からUC-04を実装し、受信→応答→配信、定期記憶整理の直線的な呼び出しを組み立てる。
4. Discord/LINEの入口を薄い変換アダプタへ変更し、共通UseCaseへ渡す。
5. Workerのチャットイベント購読、Redis EventBus、outbox、durable agent workflowを削除し、
   必要な定期起動だけを `OrganizeLongTermMemory` へ接続する。
6. teams、memberships、users管理、API管理ルーター、welcome処理など対象外の入口とUseCaseを削除する。
7. ORM、migration、DI、Docker Composeの環境変数・サービス定義を新しい依存関係へ整理する。
8. 旧モジュール、旧イベントトピック、旧ポート、旧テストを削除し、残存参照をゼロにする。

## 5. 失敗時の扱い

- 入力を受け付けられない場合は受付失敗として確定し、応答作成を開始しない。
- 応答を作成できない場合は応答不能の結果を作成する。
- 外部検索に失敗した場合は、利用可能な文脈だけで回答するか応答不能にする。
- 配信に失敗した場合は配信失敗として返す。
- 記憶整理に失敗した場合はその回を失敗として確定する。
- いずれも自動retry、回復、永続待機、バックグラウンド再実行は行わない。

## 6. 削除対象（明示）

次の機能は、ユースケース文書の対象外であるため一括改修で撤去する。

- `src/app/usecases/agent/*` と `src/app/application/agent/*`
- `src/app/usecases/messaging/dispatch_outbox_messages.py`
- `src/app/usecases/teams/*`、`memberships/*`、`users/*`
- `src/app/presentation/worker/handlers/agent_*`、`tool_*`、`outbox_*`、管理系ハンドラ
- `ConversationCoordinator`、`AgentRun`、`AgentToolCall`、outbox、lease/retry関連のORMと契約
- Discord/LINE固有の会話集約・TPH別名。チャネル送信アダプタ自体は残す。

削除前に新UseCaseから参照されていないことを検索で確認し、削除後にimport、DI、migration、
テストからも旧名が残っていないことを確認する。

## 7. 受入条件

### 業務シナリオ

- Discord、LINEの各テキスト入力が同じUC-01を通り、利用者・会話に正しく紐づく。
- 受付済みメッセージからUC-02が履歴、3種類の記憶、必要な外部情報を使って一つの結果を作る。
- 正常結果と応答不能結果の双方をUC-03が元チャネルへ届ける。
- 同一利用者の過去履歴・profile・episode・entity/relationshipが別利用者へ混入しない。
- 定期契機でUC-04を実行すると、3種類の記憶が更新される。
- 各失敗シナリオが即時失敗になり、再試行用状態を生成しない。

### 構造・品質

- 4 UseCase以外に、利用者向け業務ユースケースとして同等の入口が存在しない。
- UseCaseが特定チャネル、ORM、AI provider、ファイル形式を直接参照しない。
- `uv run pytest`、`uv run ruff check .`、`uv run pyright` が成功する。
- 不要な旧ファイル、旧イベント名、旧テーブルへの参照が `rg` で検出されない。
- Docker Composeを再ビルドして、受信・応答・配信・記憶整理の基本シナリオが起動する。

## 8. 実装前に固定する判断

この計画では、次を追加要件として扱わない。

- 自発的通知、グループ会話、メディア入力
- 管理画面・組織管理・認証認可の拡張
- 配送保証、重複排除の高度化、障害復旧、監視基盤
- 複数AIモデルの同時利用やprovider固有機能

これらが必要になった場合は、4つの業務ユースケースへの影響を再評価してから別計画とする。
