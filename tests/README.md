# tests

このフォルダにはテストコードが含まれています。

- `domain/`: ドメインモデル（集約、値オブジェクト）の単体テスト。
- `usecases/`: ユースケース（アプリケーションロジック）のテスト。
- `infrastructure/`: データベース、リポジトリ、外部サービス連携の統合テスト。
- `scenarios/`: 実際の外部AI APIを呼ぶシナリオテスト。`RUN_SCENARIO_TESTS=1` でのみ実行する。
- `presentation/`: 各エントリポイント（API, Bot, Worker）のテスト。
- `conftest.py`: pytestの共通フィクスチャ定義。
