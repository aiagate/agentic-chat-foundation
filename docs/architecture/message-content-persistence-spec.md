# Message Content Persistence Spec

この文書は、`TEXT` 系メッセージの永続化仕様と、残っている互換性を定義する。

## 目的

- assistant が複数の `contents` を返したとき、その粒度を永続化でも保持する
- 既存の `payload.text` 形式を、読み出し側だけは壊さずに扱う
- 将来の互換削除条件を明確にする

## 正式な書き込み形式

- 新規に永続化する assistant 生成メッセージは `payload.texts` を使う
- `payload.texts` は `list[str]` とする
- 空文字は保存前に除外する
- `payload.text` は新規の書き込み形式としては使わない

## 残存する互換形式

- 既存データには `payload.text` が残っている
- 読み出し側は `payload.text` と `payload.texts` の両方を受理する
- 互換はあくまで移行期間のための残存仕様であり、恒久仕様ではない

## 互換を持つ経路

- `MessageContent.from_primitive()`
- `render_message_content_text()`
- `RunAgentTurnHandler` の saved chat から prompt を復元する経路
- `chat_history_query` の履歴整形
- `memory_consolidation` の raw chat log 文字列化

## 互換を持たない経路

- 新規保存時の assistant 返信
- `RunAgentTurnHandler` が保存する generated reply

## 削除条件

次の 2 条件を満たしたら、`payload.text` の互換は削除対象とする。

1. `chats` と派生データから `payload.text` が消えていることを確認できる
2. `payload.text` を含む既存レコードへの回帰テストが不要になる

## 補足

- この仕様は `TEXT` のみ対象とする
- `IMAGE` / `STICKER` / `EMOJI` は従来どおり 1 payload で扱う
- `MessageContent.text()` は単発の入力用に残す
- `MessageContent.texts()` は複数単位の永続化用に使う
