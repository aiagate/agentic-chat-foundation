"""Persist the canonical owner on every conversation row.

Revision ID: 202607141600
Revises: 202607141500
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from ulid import ULID

from alembic import op

revision: str = "202607141600"
down_revision: str | Sequence[str] | None = "202607141500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _unresolved_legacy_chat_ids(connection: Connection) -> list[str]:
    """Return legacy rows whose provider participant identity is unavailable."""

    legacy_chats = sa.table(
        "chats",
        sa.column("id", sa.String(length=26)),
        sa.column("external_participant_id", sa.String(length=255)),
    )
    rows = (
        connection.execute(
            sa.select(legacy_chats.c.id).where(
                sa.or_(
                    legacy_chats.c.external_participant_id == "unknown",
                    legacy_chats.c.external_participant_id.is_(None),
                    sa.func.length(sa.func.trim(legacy_chats.c.external_participant_id))
                    == 0,
                )
            )
        )
        .scalars()
        .all()
    )
    return [str(row_id) for row_id in rows]


def upgrade() -> None:
    """Backfill and then require the canonical owner of each chat row."""

    # ``202607141200`` uses ``unknown`` when an old chat row has no provider
    # participant id.  Treating that sentinel as a real identity would merge
    # every unidentifiable conversation into one canonical User and would make
    # long-term memory cross user boundaries.  Refuse the migration until an
    # operator has resolved or quarantined those rows explicitly.
    connection = op.get_bind()
    unresolved_rows = _unresolved_legacy_chat_ids(connection)
    if unresolved_rows:
        sample_ids = ", ".join(str(row_id) for row_id in unresolved_rows[:10])
        raise RuntimeError(
            "Cannot assign canonical owners to legacy chat rows with an "
            "unresolved external participant identity. Resolve or quarantine "
            f"{len(unresolved_rows)} row(s) before retrying migration; "
            f"sample chat ids: {sample_ids}"
        )

    op.add_column(
        "chats",
        sa.Column("user_id", sa.String(length=26), nullable=True),
    )
    chats = sa.table(
        "chats",
        sa.column("id", sa.String(length=26)),
        sa.column("channel", sa.String(length=20)),
        sa.column("external_participant_id", sa.String(length=255)),
        sa.column("user_id", sa.String(length=26)),
    )
    identities = sa.table(
        "user_channel_identities",
        sa.column("channel", sa.String(length=20)),
        sa.column("external_participant_id", sa.String(length=255)),
        sa.column("user_id", sa.String(length=26)),
    )
    users = sa.table("users", sa.column("id", sa.String(length=26)))

    owner_by_identity = {
        (str(row.channel), str(row.external_participant_id)): str(row.user_id)
        for row in connection.execute(sa.select(identities)).mappings()
    }
    known_user_ids = {
        str(row.id) for row in connection.execute(sa.select(users)).mappings()
    }

    rows = connection.execute(sa.select(chats)).mappings().all()
    for row in rows:
        identity_key = (str(row["channel"]), str(row["external_participant_id"]))
        user_id = owner_by_identity.get(identity_key)
        if user_id is None:
            user_id = str(ULID())
            connection.execute(sa.insert(users).values(id=user_id))
            connection.execute(
                sa.insert(identities).values(
                    channel=identity_key[0],
                    external_participant_id=identity_key[1],
                    user_id=user_id,
                )
            )
            owner_by_identity[identity_key] = user_id
            known_user_ids.add(user_id)
        elif user_id not in known_user_ids:
            raise RuntimeError(f"Identity mapping points to missing user {user_id!r}")
        connection.execute(
            sa.update(chats).where(chats.c.id == row["id"]).values(user_id=user_id)
        )

    with op.batch_alter_table("chats", schema=None) as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.String(length=26),
            nullable=False,
        )
        batch_op.create_index("ix_chats_user_id", ["user_id"])
        batch_op.create_foreign_key(
            "fk_chats_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Remove the persisted owner column."""

    with op.batch_alter_table("chats", schema=None) as batch_op:
        batch_op.drop_constraint("fk_chats_user_id_users", type_="foreignkey")
        batch_op.drop_index("ix_chats_user_id")
        batch_op.drop_column("user_id")
