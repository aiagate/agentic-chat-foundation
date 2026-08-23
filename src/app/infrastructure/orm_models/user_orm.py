"""Persistence models for canonical users and channel identities."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String, func
from sqlmodel import Field, SQLModel


class UserORM(SQLModel, table=True):
    """Minimal canonical conversation owner."""

    __tablename__ = "users"  # type: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, max_length=26)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )


class UserChannelIdentityORM(SQLModel, table=True):
    """Mapping from a provider participant id to one canonical user."""

    __tablename__ = "user_channel_identities"  # type: ignore[reportAssignmentType]

    channel: str = Field(
        sa_column=Column(String(20), primary_key=True, nullable=False),
    )
    external_participant_id: str = Field(
        sa_column=Column(String(255), primary_key=True, nullable=False),
    )
    user_id: str = Field(
        sa_column=Column(
            String(26),
            ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('discord', 'line')",
            name="ck_user_channel_identities_channel",
        ),
        CheckConstraint(
            "length(trim(external_participant_id)) > 0",
            name="ck_user_channel_identities_external_participant_id",
        ),
    )
