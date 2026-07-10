"""ORM model for transactional outbox messages."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, func
from sqlmodel import Field, SQLModel


class OutboxMessageORM(SQLModel, table=True):
    """Durable event published asynchronously after transaction commit."""

    __tablename__ = "outbox_messages"  # type: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, max_length=36)
    topic: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    payload: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            index=True,
        ),
    )
    published_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    attempt_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, default=0),
    )
    next_attempt_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    claimed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    claim_token: str | None = Field(
        default=None,
        sa_column=Column(String(36), nullable=True, index=True),
    )
    last_error: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
