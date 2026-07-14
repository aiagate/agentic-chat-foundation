# API層 実装ガイドライン

現行アプリケーションはDiscord DMとLINE webhookを主な外部入口とし、管理APIを提供しない。
将来HTTP APIを追加する場合も、チャネルアダプタと同じくUseCaseの薄い入口として実装する。

## アーキテクチャ上の位置づけ

API層（`src/app/presentation/api`）はプレゼンテーション層に位置する。

- HTTPリクエストを共通メッセージへ変換し、適切なUseCaseを呼び出す。
- API層へ業務ロジック、ORM操作、外部SDK呼び出しを置かない。
- UseCaseの結果をHTTPレスポンスへ変換する。

許可される依存方向は次の通り。

```text
presentation/api -> usecases -> contracts/domain
```

APIからinfrastructureを直接参照してはならない。

## 対象となるUseCase

会話をHTTP入口へ公開する場合は、次の順序を一つの要求処理として利用する。

1. `AcceptIncomingMessage`
2. `CreateConversationResponse`
3. `DeliverConversationResult`

長期記憶の管理や組織・team・membership・userの管理APIは、現在の対象外である。

## CommandとQuery

- Commandは状態を変更し、UseCaseが定義した結果DTOを返す。
- Queryは読み取りだけを行い、別の副作用を持たない。
- DTOは`contracts/messages`またはAPI専用のPydanticモデルで表す。
- APIは`Result`の成功・失敗を適切なHTTPステータスへ変換する。

## エラー

- 入力検証失敗: 400 Bad Request
- 対象が存在しない: 404 Not Found
- 外部サービス・永続化の即時失敗: 500 Internal Server Error

自動retry、永続待機、復旧用APIは追加しない。失敗はUseCaseの結果としてその場で確定する。
