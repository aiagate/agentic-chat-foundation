# Domain層ドキュメント

Domain層には、会話・記憶の業務ルールと、それらを表す値・契約を置く。

## 配置

- `src/app/domain/value_objects/`: ドメイン値オブジェクト
- `src/app/domain/repositories/`: repository/queryのDomain契約
- `src/app/contracts/ports/`: UseCaseが依存するアプリケーション境界
- `src/app/contracts/messages/`: layerをまたぐDTO

AI、memory、tool、会話送信などのアプリケーション境界契約は`contracts/ports`へ置く。

## 現行の業務境界

会話処理では、チャネル差異をDomainモデルへ持ち込まず、共通のメッセージ契約を使う。
入口は次のUseCaseである。

- `AcceptIncomingMessage`
- `CreateConversationResponse`
- `DeliverConversationResult`
- `OrganizeLongTermMemory`

User/Team/TeamMembership管理は対象外であり、会話UseCaseから参照しない。

## 実装方針

- Domain層は純粋なPythonオブジェクトに保つ。
- 値オブジェクトは`from_primitive` / `to_primitive`を実装する。
- 外部SDK、ORM、ファイル形式はDomain層へ持ち込まない。
- 詳細な配置規則は[Domain実装ガイド](./domain-implementation-guide.md)を参照する。
