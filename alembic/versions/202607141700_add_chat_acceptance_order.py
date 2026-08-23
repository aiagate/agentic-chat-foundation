"""Add a database-allocated acceptance order key for turn boundaries.

Revision ID: 202607141700
Revises: 202607141600
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607141700"
down_revision: str | Sequence[str] | None = "202607141600"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make acceptance order explicit and monotonic for every chat row."""

    connection = op.get_bind()
    is_postgresql = connection.dialect.name == "postgresql"
    if is_postgresql:
        op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS chat_acceptance_sequence"))

    column = sa.Column(
        "accepted_sequence",
        sa.BigInteger(),
        nullable=True,
        server_default=(
            sa.text("nextval('chat_acceptance_sequence')") if is_postgresql else None
        ),
    )
    op.add_column("chats", column)

    chats = sa.table(
        "chats",
        sa.column("id", sa.String(length=26)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("accepted_sequence", sa.BigInteger()),
    )
    rows = connection.execute(
        sa.select(chats.c.id).order_by(chats.c.created_at, chats.c.id)
    ).scalars()
    next_order_key = 1
    for chat_id in rows:
        connection.execute(
            sa.update(chats)
            .where(chats.c.id == chat_id)
            .values(accepted_sequence=next_order_key)
        )
        next_order_key += 1

    with op.batch_alter_table("chats", schema=None) as batch_op:
        batch_op.alter_column(
            "accepted_sequence",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
        batch_op.create_index(
            "ix_chats_accepted_sequence",
            ["accepted_sequence"],
        )

    if is_postgresql:
        current = max(next_order_key - 1, 1)
        statement = sa.text(
            "SELECT setval('chat_acceptance_sequence', :value, true)"
        ).bindparams(value=current)
        op.execute(statement)


def downgrade() -> None:
    """Remove the acceptance order key."""

    connection = op.get_bind()
    with op.batch_alter_table("chats", schema=None) as batch_op:
        batch_op.drop_index("ix_chats_accepted_sequence")
        batch_op.drop_column("accepted_sequence")
    if connection.dialect.name == "postgresql":
        op.execute(sa.text("DROP SEQUENCE IF EXISTS chat_acceptance_sequence"))
