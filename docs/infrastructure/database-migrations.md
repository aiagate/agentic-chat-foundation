# データベースマイグレーションガイド

> 本書はデータベース変更を扱う技術 runbook であり、業務上の概念やユースケースの正本ではない。
> スキーマの現在状態は、実行時のマイグレーション履歴とリポジトリ内の migration を確認する。
> 以下の `uv run` コマンドは開発コンテナ内で実行する。ホスト上でアプリケーションを単体起動しない。

> 本文中のコード例はマイグレーションの手順を説明するための一般例であり、現在のスキーマを表さない。
> 実際に適用する差分は、リポジトリ内の migration と実行時の Alembic 履歴を正本とする。

最終更新日: 2026-07-16

このドキュメントは、Alembicを使用したデータベースマイグレーションの作成・管理方法を説明します。

---

## 目次

- [概要](#概要)
- [マイグレーション作成の基本フロー](#マイグレーション作成の基本フロー)
- [現在状態とdrift確認](#現在状態とdrift確認)
- [マイグレーションパターン](#マイグレーションパターン)
- [よくあるケース](#よくあるケース)
- [トラブルシューティング](#トラブルシューティング)
- [ベストプラクティス](#ベストプラクティス)

---

## 概要

### Alembicとは

[Alembic](https://alembic.sqlalchemy.org/) は、SQLAlchemyのためのデータベースマイグレーションツールです。このプロジェクトでは、SQLModelと組み合わせて使用しています。

### プロジェクトの構成

```
.
├── alembic/
│   ├── env.py                # Alembic環境設定
│   ├── script.py.mako        # マイグレーションファイルのテンプレート
│   └── versions/             # マイグレーションファイル格納ディレクトリ
├── alembic.ini               # Alembic設定ファイル
└── src/app/
    └── infrastructure/
        └── orm_models/       # SQLModel ORMモデル
```

### データベース設定

- **開発環境**: SQLite (`bot.db`)
- **本番環境**: 環境変数 `DATABASE_URL` で指定
- **非同期対応**: `aiosqlite` / `asyncpg` を使用
- **現行のmigration head**: 実行時に `uv run --frozen alembic heads` で確認する。
- 利用者とチャネル上の利用者識別子の初期登録は、[User Identity Mapping](user-identity-mapping.md)を参照する。
- 会話 `TEXT` payload の正規化は `202607141500_normalize_message_content_texts.py` で実施する。
- chatのキャラクター境界と関係状態・シグナル表は `202607151500_add_character_relationships.py` で追加する。既存chatは`shirasagi-reina`へ割り当て、旧関係scoreは移行しない。

---

## マイグレーション作成の基本フロー

### 1. ORMモデルの変更

まず、`src/app/infrastructure/orm_models/` 配下のORMモデルを変更します。

例: `chat_orm.py`

```python
class ChatORM(SQLModel, table=True):
    __tablename__ = "chats"

    channel: str = Field(max_length=20, index=True)
    external_conversation_id: str = Field(max_length=255, index=True)
    external_participant_id: str = Field(max_length=255, index=True)
```

### 2. マイグレーションファイルの生成

```bash
uv run --frozen alembic revision -m "変更内容の説明"
```

例:

```bash
uv run --frozen alembic revision -m "rename user name to display name"
```

生成されるファイル:

```
alembic/versions/d71330ad48f7_rename_user_name_to_display_name.py
```

### 3. マイグレーションコードの実装

生成されたファイルの `upgrade()` と `downgrade()` 関数を実装します。

```python
def upgrade() -> None:
    """Upgrade schema."""
    # アップグレード処理を実装

def downgrade() -> None:
    """Downgrade schema."""
    # ダウングレード処理を実装
```

### 4. マイグレーションの実行

```bash
# 現在の状態を確認
uv run --frozen alembic current

# リポジトリ上のheadを確認
uv run --frozen alembic heads

# ORMモデルとmigrationの差分を確認
uv run --frozen alembic check

# マイグレーションを実行
uv run --frozen alembic upgrade head

# マイグレーション履歴を確認
uv run --frozen alembic history
```

### 5. ロールバックのテスト

```bash
# 1つ前にロールバック
uv run --frozen alembic downgrade -1

# 再度アップグレード
uv run --frozen alembic upgrade head
```

---

## 現在状態とdrift確認

マイグレーション関連の作業前後では、次の順で確認します。

```bash
# DBが現在どのrevisionか確認
uv run --frozen alembic current

# リポジトリにある最新headを確認
uv run --frozen alembic heads

# DBを最新headまで適用
uv run --frozen alembic upgrade head

# ORMモデルとmigrationのdriftを検出
uv run --frozen alembic check
```

`current` と `heads` が一致していない場合は、まず `upgrade head` でローカルDBを
最新化します。その後に `check` を実行し、ORMモデル変更に対して未作成の
マイグレーションが残っていないことを確認します。

### migration drift がある場合

`uv run --frozen alembic check` が差分を検出した場合は、既存のmigrationを編集せず、
follow-up migrationを新規作成します。

```bash
uv run --frozen alembic revision --autogenerate -m "describe detected schema drift"
```

生成後は以下を必ず行います。

1. `upgrade()` と `downgrade()` が意図した差分だけを含むか確認する。
2. SQLite互換性が必要な操作は手動で安全な手順に修正する。
3. `uv run --frozen alembic upgrade head` を実行する。
4. `uv run --frozen alembic check` が差分なしになることを確認する。
5. 必要に応じて `uv run --frozen alembic downgrade -1` から再度 `upgrade head` する。

既に共有・適用済みのmigrationはimmutableとして扱います。過去revisionの誤りを
見つけた場合も、そのファイルを書き換えず、新しいrevisionで補正します。

---

## マイグレーションパターン

### テーブル作成

```python
def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=26), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

def downgrade() -> None:
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
```

### カラム追加

```python
def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(length=20), nullable=True))

def downgrade() -> None:
    op.drop_column('users', 'phone')
```

### カラム名変更（SQLite対応）

**重要**: SQLiteは `ALTER COLUMN` を直接サポートしていないため、以下のパターンを使用します。

```python
import sqlalchemy as sa

def upgrade() -> None:
    """Rename name column to display_name (SQLite compatible)."""
    # Step 1: インデックスを削除（存在する場合）
    op.drop_index(op.f('ix_users_name'), table_name='users')

    # Step 2: 新しいカラムを追加
    op.add_column('users', sa.Column('display_name', sa.String(length=255), nullable=True))

    # Step 3: データをコピー
    op.execute('UPDATE users SET display_name = name')

    # Step 4: 古いカラムを削除
    op.drop_column('users', 'name')

    # Step 5: 新しいインデックスを作成
    op.create_index(op.f('ix_users_display_name'), 'users', ['display_name'], unique=False)

def downgrade() -> None:
    """Revert display_name column back to name (SQLite compatible)."""
    op.drop_index(op.f('ix_users_display_name'), table_name='users')
    op.add_column('users', sa.Column('name', sa.String(length=255), nullable=True))
    op.execute('UPDATE users SET name = display_name')
    op.drop_column('users', 'display_name')
    op.create_index(op.f('ix_users_name'), 'users', ['name'], unique=False)
```

### カラム型変更（SQLite対応）

```python
def upgrade() -> None:
    """Change timestamp columns to datetime type (SQLite compatible)."""
    # Step 1: 新しい型のカラムを追加
    op.add_column(
        'users',
        sa.Column('created_at_new', sa.DateTime(timezone=True), server_default=sa.func.now())
    )

    # Step 2: データを変換してコピー
    op.execute(
        "UPDATE users SET created_at_new = datetime(created_at)"
    )

    # Step 3: 古いカラムを削除
    op.drop_column('users', 'created_at')

    # Step 4: 新しいカラムをリネーム
    op.alter_column('users', 'created_at_new', new_column_name='created_at')

def downgrade() -> None:
    """Revert datetime columns back to string type."""
    op.add_column('users', sa.Column('created_at_new', sa.String(), nullable=True))
    op.execute("UPDATE users SET created_at_new = created_at")
    op.drop_column('users', 'created_at')
    op.alter_column('users', 'created_at_new', new_column_name='created_at')
```

### プライマリキーの変更

**警告**: プライマリキーの変更は破壊的な操作です。既存データの扱いに注意してください。

```python
def upgrade() -> None:
    """Change user id from int to ULID (string)."""
    # データを削除（開発環境のみ推奨）
    op.execute('DELETE FROM users')

    # 主キー制約を削除
    op.drop_constraint('users_pkey', 'users', type_='primary')
    op.drop_column('users', 'id')

    # 新しいカラムを追加
    op.add_column(
        'users',
        sa.Column('id', sa.String(length=26), nullable=False),
    )

    # 主キー制約を再作成
    op.create_primary_key('users_pkey', 'users', ['id'])

def downgrade() -> None:
    """Revert user id back from ULID to int."""
    op.execute('DELETE FROM users')
    op.drop_constraint('users_pkey', 'users', type_='primary')
    op.drop_column('users', 'id')
    op.add_column(
        'users',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
    )
    op.create_primary_key('users_pkey', 'users', ['id'])
```

### インデックスの操作

```python
def upgrade() -> None:
    # インデックス作成
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 複合インデックス
    op.create_index('ix_users_name_email', 'users', ['name', 'email'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index('ix_users_name_email', table_name='users')
```

---

## よくあるケース

### 新しいテーブルを追加する

1. `src/app/infrastructure/orm_models/` に新しいORMモデルを作成
2. `alembic/env.py` でモデルをインポート（自動検出のため）
3. マイグレーションを生成:

   ```bash
   uv run --frozen alembic revision -m "add teams table"
   ```

4. 生成されたファイルを確認・編集
5. マイグレーションを実行

### 既存のテーブルにカラムを追加する

1. ORMモデルにカラムを追加
2. マイグレーションを生成:

   ```bash
   uv run --frozen alembic revision -m "add phone column to users"
   ```

3. `upgrade()` と `downgrade()` を実装
4. マイグレーションを実行

### カラム名を変更する

1. ORMモデルのカラム名を変更
2. マイグレーションを生成:

   ```bash
   uv run --frozen alembic revision -m "rename user name to display name"
   ```

3. SQLite対応のリネームパターンを実装（上記参照）
4. マイグレーションを実行

---

## トラブルシューティング

### エラー: "no such index"

**原因**: 削除しようとしているインデックスがデータベースに存在しない。

**対処法**:

1. 現在のデータベーススキーマを確認:

   ```bash
   uv run --frozen python -c "import sqlite3; conn = sqlite3.connect('bot.db'); cursor = conn.cursor(); cursor.execute('PRAGMA index_list(users)'); print(cursor.fetchall()); conn.close()"
   ```

2. マイグレーションを条件付きにするか、`alembic stamp` でマイグレーション履歴をマーク:

   ```bash
   uv run --frozen alembic stamp head
   ```

### エラー: "no such column"

**原因**: 参照しているカラムがデータベースに存在しない。

**対処法**:

1. 現在のテーブル構造を確認:

   ```bash
   uv run --frozen python -c "import sqlite3; conn = sqlite3.connect('bot.db'); cursor = conn.cursor(); cursor.execute('PRAGMA table_info(users)'); print(cursor.fetchall()); conn.close()"
   ```

2. マイグレーション順序を確認:

   ```bash
   uv run --frozen alembic history
   ```

3. 必要に応じてデータベースをリセット:

   ```bash
   rm bot.db
   uv run --frozen alembic upgrade head
   ```

### マイグレーション履歴の不整合

**対処法**:

1. 現在の状態を確認:

   ```bash
   uv run --frozen alembic current
   uv run --frozen alembic heads
   ```

2. 未適用のmigrationがある場合は最新化:

   ```bash
   uv run --frozen alembic upgrade head
   ```

3. ORMモデルとmigrationのdriftを確認:

   ```bash
   uv run --frozen alembic check
   ```

4. 特定のリビジョンにマーク:

   ```bash
   uv run --frozen alembic stamp <revision_id>
   ```

`stamp` はDBスキーマを変更せず履歴だけを更新するため、実際のスキーマが対象revision
と一致していると確認できる場合にだけ使用します。

### 開発中にスキーマが手動で変更された

**対処法**:
原則として手動変更を正とせず、ORMモデルとmigrationで再現可能な状態に戻します。
手動変更が必要な差分だった場合は、follow-up migrationとして記録します。

```bash
uv run --frozen alembic current
uv run --frozen alembic heads
uv run --frozen alembic upgrade head
uv run --frozen alembic check
uv run --frozen alembic revision --autogenerate -m "reconcile manual schema change"
```

生成されたmigrationを確認・修正したうえで `upgrade head` と `check` を再実行します。
`stamp head` は、DB実体が既にheadと一致していると確認できる復旧時に限って使います。

---

## ベストプラクティス

### 1. マイグレーションの粒度

- **1つのマイグレーションは1つの論理的な変更のみ**を含める
- 大きな変更は複数のマイグレーションに分割する
- テーブル作成とデータ投入は別々のマイグレーションにする

### 2. ダウングレードの実装

- 必ず `downgrade()` を実装する
- ダウングレードが不可能な場合（データ削除など）はコメントで明記する

### 3. データの扱い

- **破壊的な変更には十分注意する**
- データマイグレーション（既存データの変換）が必要な場合は、慎重にテストする
- 本番環境ではバックアップを取ってから実行する

### 4. SQLite互換性

- プロジェクトはSQLiteをデフォルトで使用しているため、SQLite互換のパターンを使用する
- `ALTER COLUMN` は使用せず、カラム追加 → データコピー → カラム削除のパターンを使用

### 5. テスト

マイグレーション実行後は必ずテストを実行:

```bash
uv run --frozen pytest
```

### 6. コミット前の確認

```bash
# マイグレーションをテスト
uv run --frozen alembic upgrade head
uv run --frozen alembic downgrade -1
uv run --frozen alembic upgrade head

# テストを実行
uv run --frozen pytest

# コードフォーマット
uv run --frozen ruff format .
uv run --frozen ruff check . --fix
```

### 7. マイグレーションファイルの管理

- **既存のマイグレーションファイルは絶対に変更しない**
- 共有済み・適用済みのmigrationはimmutableとして扱う
- 修正が必要な場合は新しいfollow-up migrationを作成する
- drift修正も過去revisionの編集ではなく、新規revisionで補正する
- マイグレーションファイルはバージョン管理に含める

### 8. drift確認

マイグレーションを追加・修正したら、次の確認を行う:

```bash
uv run --frozen alembic current
uv run --frozen alembic heads
uv run --frozen alembic upgrade head
uv run --frozen alembic check
```

`check` が差分を検出する場合は、ORMモデル変更に対応するmigrationが不足している。
既存migrationを編集せず、新規revisionを作成して差分を解消する。

### 9. 命名規則

マイグレーションメッセージは明確で簡潔に:

- [OK] `"add teams table"`
- [OK] `"rename user name to display name"`
- [OK] `"change timestamp columns to datetime type"`
- [NG] `"update"`
- [NG] `"fix"`

---

## 参考資料

- [Alembic公式ドキュメント](https://alembic.sqlalchemy.org/)
- [SQLModel公式ドキュメント](https://sqlmodel.tiangolo.com/)
- [SQLAlchemy公式ドキュメント](https://docs.sqlalchemy.org/)

---

## 関連ドキュメント

- [アーキテクチャ設計](../architecture/architecture-overview.md)
- [ドメイン実装ガイド](../domain/domain-implementation-guide.md)
