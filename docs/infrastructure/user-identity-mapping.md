# User Identity Mapping

> 本書は運用者が利用者の対応付けを初期登録・移行するための技術 runbook である。
> 業務上の「利用者」と「チャネル上の利用者識別子」の意味は
> [ユビキタス言語](../product/ubiquitous-language/index.md)を正本とする。
> 削除SQLは対象環境と対象データを確認してから実行する。

Discord/LINEのprovider IDと、会話・memoryが所有者として使うcanonical `User.id`を分離する。
登録機能はアプリケーションのスコープ外であり、運用者がSQLを明示的に投入する。

## IDの源流

- Discord: `discord.Message.author.id`を文字列化した値
- LINE: webhook eventの`source.user_id`

これらは`IncomingMessage.external_participant_id`としてメッセージ受付処理へ届く。メッセージ受付処理は
`(channel, external_participant_id)`を`user_channel_identities`で引き、canonical Userを解決する。
未登録の場合はraw chatを保存せず受付失敗にする。

## 初期登録SQL

`<26-char-ulid>`は運用者が事前に生成する。同一人物のDiscord/LINE IDには同じ`user_id`を指定する。

```sql
BEGIN;

INSERT INTO users (id)
VALUES ('<26-char-ulid>');

INSERT INTO user_channel_identities
    (channel, external_participant_id, user_id)
VALUES
    ('discord', '<discord-author-id>', '<26-char-ulid>'),
    ('line', '<line-source-user-id>', '<26-char-ulid>');

COMMIT;
```

対応表の一意キーは`(channel, external_participant_id)`である。一つのprovider IDを複数Userへ登録できない。
既存chatの外部IDから自動登録・自動統合はしない。

canonical owner migration は、旧chatにprovider participant IDがない場合に停止する。
`unknown` を一つのUserへ割り当てることは、異なる利用者の会話とmemoryを混ぜるため許可しない。
migrationが停止した場合は、対象chatを利用者へ明示的に対応付けるか、raw chatとmemory整理の対象外へ隔離してから再実行する。

## 会話履歴整理時の再処理

旧外部ID単位のmemoryはcanonical Userへ安全に帰属させられないため、対応表の確認後に破棄する。
対象環境ごとに次を一回実施する。

1. 上記SQLで全provider IDの対応表を登録する。
2. `memory/profiles/users/`、`memory/timeline/`、`memory/entities/`配下のuser memoryを削除する。
   `memory/profiles/agent/`は残す。
3. 派生indexと評価済みmarkerを削除する。

```sql
BEGIN;
DELETE FROM memory_index_documents WHERE user_id IS NOT NULL;
DELETE FROM memory_consolidated_chat_sources;
COMMIT;
```

次の03:00 JST実行、または`WORKER_RUN_ONCE=1`のworker起動で、SQL raw chatからcanonical User単位に再整理する。
一つでも未登録provider IDが残ると、そのIDのraw chatは会話履歴整理の対象に選ばれない。
