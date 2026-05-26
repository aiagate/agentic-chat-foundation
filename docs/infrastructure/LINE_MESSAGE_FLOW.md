# LINE メッセージフロー

このドキュメントは、LINE webhook 受信から生成返信の送信までの現行実装
フローを示す。実装上の境界は次の通り。

- LINE FastAPI process は webhook を受け取り、LINE 返信イベントも購読する。
- Worker process は保存済み LINE メッセージイベントを購読し、返信生成を起動する。
- 生成処理は `RetrieveMemoryContextQuery` 経由で記憶コンテキストを取得する。
- 検索が必要な場合は `chat.search.requested` / `chat.search.completed` を介して
  短期検索 workflow に分岐し、再推論時に `retrieved context` を追加する。
- reply-ready payload は `contents` を一次情報とし、`content` は互換用の結合値として扱う。
- 複数 process 構成では process 内メモリの EventBus では届かないため、共有 EventBus provider を使う。

```mermaid
sequenceDiagram
    autonumber
    actor User as LINEユーザー
    participant LINE as LINE Platform
    participant API as LINE FastAPI process<br/>presentation.line.__main__
    participant Parser as WebhookParser
    participant Mediator as Mediator
    participant SaveUC as SaveLineChatHandler
    participant DB as Chat Repository / UoW
    participant Bus as EventBus
    participant Worker as Worker process<br/>presentation.worker.__main__
    participant GenUC as GenerateContentHandler
    participant SearchUC as HandleSearchRequestHandler
    participant SearchExec as RunWebSearchHandler
    participant RegenUC as GenerateContentWithRetrievedContextHandler
    participant RetrieveMemory as RetrieveMemoryContextQuery
    participant Memory as IMemoryService
    participant AI as IAIService<br/>Mock/GPT/Gemini
    participant Sender as send_line_reply
    participant LINEAPI as AsyncMessagingApi

    User->>LINE: メッセージ送信
    LINE->>API: POST /callback<br/>X-Line-Signature + body
    API->>Parser: parse(body, signature)

    alt 署名不正
        Parser-->>API: InvalidSignatureError
        API-->>LINE: 400 Invalid signature
    else 署名OK
        Parser-->>API: events
        API->>API: MessageEvent かつ TextMessageContent か確認
        API->>API: UserSource.user_id を取得

        alt user_idなし / 非対応イベント
            API-->>LINE: OK
        else user_idあり
            API->>Mediator: SaveLineChatCommand(user_id, content)
            Mediator->>SaveUC: handle(command)
            SaveUC->>DB: LineChat.create_user_chat<br/>Repository.add()
            SaveUC->>DB: commit()

            alt 保存失敗
                SaveUC-->>API: Err
                API->>LINEAPI: reply_message(replyToken,<br/>"メッセージの保存に失敗しました。")
                LINEAPI-->>User: 保存失敗メッセージ
            else 保存成功
                SaveUC->>Bus: publish chat.line.saved<br/>{chat_id,user_id,content}
                SaveUC-->>API: Ok(SaveChatResult)
                API-->>LINE: OK

                Bus->>Worker: on_line_chat_saved(payload)
                Worker->>Mediator: GenerateContentQuery<br/>chat_type=LINE
                Mediator->>GenUC: handle(query)

                GenUC->>DB: GetChatHistoryQuery()<br/>get_recent_history(LINE, limit=20)
                GenUC->>RetrieveMemory: Mediator.send_async<br/>RetrieveMemoryContextQuery(query,user_id)
                RetrieveMemory->>Memory: retrieve(query, user_id)
                Memory-->>RetrieveMemory: MemoryContextPack
                RetrieveMemory-->>GenUC: assembled_context
                GenUC->>AI: generate_content(prompt, history,<br/>system_instruction=assembled_context)
                AI-->>GenUC: GeneratedContent(contents)
                alt tool requestなし
                    GenUC->>DB: LineChat.create_user_chat<br/>MessageContent.text(join(contents))
                    GenUC->>DB: commit()
                    GenUC->>Bus: publish chat.line.reply_ready<br/>{chat_type,user_id,contents,content}
                else tool requestあり
                    GenUC->>Bus: publish chat.search.requested<br/>{search_session_id,chat_type,prompt,query,user_message}

                    Bus->>Worker: on_chat_search_requested(payload)
                    Worker->>Mediator: HandleSearchRequestCommand
                    Mediator->>SearchUC: handle(command)
                    SearchUC->>Mediator: RunWebSearchCommand
                    Mediator->>SearchExec: handle(command)
                    SearchExec->>SearchExec: Ollama Web Search
                    SearchExec->>SearchExec: save retrieved context
                    SearchUC->>Bus: publish chat.search.completed<br/>{search_session_id,chat_type,prompt,status,result_count}

                    Bus->>Worker: on_chat_search_completed(payload)
                    Worker->>Mediator: GenerateContentWithRetrievedContextQuery
                    Mediator->>RegenUC: handle(query)
                    RegenUC->>DB: GetChatHistoryQuery()<br/>get_recent_history(LINE, limit=20)
                    RegenUC->>RetrieveMemory: Mediator.send_async<br/>RetrieveMemoryContextQuery(query,user_id)
                    RetrieveMemory->>Memory: retrieve(query, user_id)
                    Memory-->>RetrieveMemory: MemoryContextPack
                    RegenUC->>RegenUC: load retrieved context by search_session_id
                    RegenUC->>AI: generate_content(prompt, history,<br/>system_instruction=memory+retrieved context)
                    AI-->>RegenUC: GeneratedContent(contents)
                    RegenUC->>DB: LineChat.create_user_chat<br/>MessageContent.text(join(contents))
                    RegenUC->>DB: commit()
                    RegenUC->>Bus: publish chat.line.reply_ready<br/>{chat_type,user_id,contents,content}
                end

                Bus->>API: subscribed chat.line.reply_ready
                API->>Sender: send_line_reply(line_bot_api, payload)
                Sender->>Sender: normalize contents first<br/>fallback to content
                loop content in contents
                    Sender->>LINEAPI: push_message(to=user_id, TextMessage)
                    LINEAPI-->>User: 生成返信
                end
            end
        end
    end
```

## EventBus provider の注意点

LINE flow は少なくとも LINE FastAPI process と Worker process に分かれる。`chat.line.saved`
は LINE process から publish され、Worker process が購読する。`chat.line.reply_ready`
は Worker process から publish され、LINE process が購読して `send_line_reply` を実行する。

このため、複数 process で動かす環境では `EVENT_BUS_PROVIDER=redis` または
`EVENT_BUS_PROVIDER=postgres` のように process 間で共有できる provider を設定する。
`memory` provider は同一 process 内でしかイベントを配送できないため、LINE と Worker を
別 process で起動すると保存イベントや返信準備イベントが相手 process に届かない。

`REDIS_URL` が設定されている場合は Redis provider が優先され、PostgreSQL の
`DATABASE_URL` が設定されている場合は Postgres provider が選ばれる。明示する場合は
`EVENT_BUS_PROVIDER` を設定して、LINE process と Worker process で同じ provider と
接続先を使う。
