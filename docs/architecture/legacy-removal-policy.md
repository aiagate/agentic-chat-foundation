# Legacy Removal Policy

この文書は、役目を終えた実装をどのように扱うかを定義する。
目的は、移行のために残した互換コードが恒久化するのを防ぐことである。

## 基本方針

- レガシーは「残すかもしれない資産」ではなく、「削除候補」である。
- 互換性維持は移行のための一時措置に限る。
- 役目を終えた実装は、git で戻せる前提で削除する。
- 残す理由が曖昧なコードは、実際には不要である可能性が高い。

## 削除の判断基準

次の 2 条件を満たせるなら、原則として削除する。

1. 未移行の呼び出し元が残っていないことを確認できる。
2. 削除後に回帰テストで挙動を確認できること。

どちらかが満たせない場合は、削除ではなく移行計画の補完を先に行う。

## 残してよいもの

- 移行中の一時的なアダプタ
- 新旧両方の呼び出し元を支えるために必要な最小限の互換層
- テスト用のフィクスチャや PoC のための限定的な mock

ただし、これらも移行完了後は削除対象である。

## 残してはいけないもの

- 目的が消えた重複実装
- 新しい層を作った後も残った古い facade
- 参照されなくなった helper、utility、schema 定義
- 名前だけ残って実態が誤認を生むモジュール

## レガシー削除の進め方

1. 依存の流れを確認する。
2. 新しい置き場に実装を移す。
3. 呼び出し元をすべて新しい経路へ更新する。
4. テストを通して動作を確認する。
5. 旧実装を削除する。
6. README や棚卸文書から旧実装名を消す。

## 判定に使う証拠

削除判断は印象ではなく証拠で行う。

- `rg` による参照残りの有無
- テストの成功
- 実行コマンドの成功
- 生成物や migration の存在
- 置き換え後の import 経路

## このリポジトリでの具体例

- `src/app/contracts/messages/tool_use.py` は削除され、tool の共有 DTO は `src/app/contracts/messages/tool_contracts.py` に集約された。
- `src/app/contracts/ports/search_context_store.py` は削除され、短期 retrieved context の契約は `src/app/contracts/ports/retrieved_context_store.py` に移った。
- `src/app/infrastructure/services/search_context_store.py` は削除され、実装は `src/app/infrastructure/stores/retrieved_context_store.py` に移った。
- `src/app/infrastructure/services/memory_store.py` は削除され、Markdown memory の低レベル I/O は `src/app/infrastructure/memory/store.py` に移った。
- `src/app/infrastructure/services/memory_index.py` は削除され、検索は `src/app/infrastructure/queries/memory_index_query_service.py` と `src/app/infrastructure/repositories/memory_index_repository.py` に分離された。
- `src/app/usecases/search/handle_search_request.py` は削除され、generic tool flow は `src/app/usecases/agent/route_tool_calls.py` と `src/app/usecases/agent/handle_tool_execution.py` に集約された。

## 例外

次の場合のみ、一時的にレガシーを残してよい。

- 呼び出し元の移行がまだ完了していない
- 削除すると検証手段が消える
- 外部リリースとの整合を取るために短期間必要

ただし例外は期限付きである。期限を過ぎたら削除する。

## レビュー基準

- これは本当に互換性維持のために必要か。
- 新しい経路に置き換えた後も残す意味があるか。
- 削除してもテストで確認できるか。
- 名前が残っているだけで誤認を生んでいないか。

## 運用ルール

- 互換層を追加する前に、削除条件を先に書く。
- 置換が終わったら、削除を延期しない。
- README や棚卸文書に古い名前が残っていたら、実装と同じ優先度で直す。
- 「いつか消す」は禁止し、消す条件を明文化する。
