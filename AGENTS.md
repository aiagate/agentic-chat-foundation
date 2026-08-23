# 開発ガイドライン (Development Guidelines)

本ドキュメントは、このコードベースで作業する際の重要な情報をまとめたものです。これらの指針を厳密に遵守してください。

教義の詳細は以下を参照してください。
- [Service Role Guidelines](docs/architecture/service-role-guidelines.md)
- [Storage and Query Boundaries](docs/architecture/storage-and-query-boundaries.md)
- [Legacy Removal Policy](docs/architecture/legacy-removal-policy.md)

## 開発の基本ルール


- `uv` のみを使用すること。 `pip` は絶対に使用しないこと。
- 型ヒント: すべてのコードに必須とする。
- ファイル、クラス、関数はその責務に集中させ、小さく保つこと。
- UseCaseは外部からの要求を受ける入口とする。
- UseCase内で再利用したい処理は、別のUseCaseとして扱わず、その処理固有の責務へ切り出すこと。
- 複数のUseCase相当の処理を束ねる必要がある場合は、実装前に設計を相談すること。

## ベストプラクティス

- 起動は常に Docker コンテナで行うこと。単体起動の手順は追加しない。
- コード変更後は `docker compose up --build -d` で再ビルド再起動すること。
- レガシーになったコードは即削除する(Gitからいつでも復元可能であるため)
- 依存の方向性をまず確認すること。何かを置く前に「どこからどこへ依存してよいか」を仮定として明示し、その方向に合わせて配置を決める。
  `IAIService` や `IEventBus` のようなアプリケーション境界のインターフェース契約は `src/app/contracts/ports` に置く。
  `GeneratedContent` や `chat_events` のように複数レイヤーから参照されるDTO・イベントトピック・ペイロードビルダーは `src/app/contracts/messages` に置く。
  `domain/interfaces` を汎用的な契約置き場として使わない。ドメイン固有の抽象だけをドメイン配下に残し、ユースケース固有でない共有境界型を `usecases` に逃がさない。
- 徹底的に型チェックとテストを行う。
- 名前は責務を示すべきで、配置は名前を裏切ってはいけない
- 複雑さは薄い層に押し込まず、責務に応じて層を分ける
- 派生データの永続化は、実装ファイルではなく migration で扱う
- 誤認を生む構造は、動いていても欠陥とみなす
