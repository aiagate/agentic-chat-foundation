"""Persistence models for character relationship state and evidence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlmodel import Field, SQLModel


class CharacterRelationshipORM(SQLModel, table=True):
    """Current affection snapshot for one character and user."""

    __tablename__ = "character_relationships"  # type: ignore[reportAssignmentType]

    character_id: str = Field(
        sa_column=Column(String(100), primary_key=True, nullable=False)
    )
    user_id: str = Field(
        sa_column=Column(
            String(26),
            ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    affection: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, default=0),
    )
    version: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, default=1),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
        ),
    )

    __table_args__ = (
        CheckConstraint(
            "affection >= 0 AND affection <= 100",
            name="ck_character_relationships_affection",
        ),
        CheckConstraint("version >= 1", name="ck_character_relationships_version"),
    )


class RelationshipSignalEventORM(SQLModel, table=True):
    """Auditable semantic relationship signal."""

    __tablename__ = "relationship_signal_events"  # type: ignore[reportAssignmentType]

    id: str = Field(sa_column=Column(String(64), primary_key=True, nullable=False))
    character_id: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    user_id: str = Field(sa_column=Column(String(26), nullable=False, index=True))
    kind: str = Field(sa_column=Column(String(32), nullable=False))
    status: str = Field(sa_column=Column(String(16), nullable=False, index=True))
    confidence: float = Field(nullable=False)
    proposed_delta: int = Field(sa_column=Column(Integer, nullable=False))
    applied_delta: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, default=0),
    )
    reason: str = Field(default="", sa_column=Column(String(1000), nullable=False))
    observed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["character_id", "user_id"],
            [
                "character_relationships.character_id",
                "character_relationships.user_id",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('provisional', 'confirmed', 'superseded')",
            name="ck_relationship_signal_events_status",
        ),
        CheckConstraint(
            "kind IN ('strong_negative', 'negative', 'neutral', 'positive', 'strong_positive')",
            name="ck_relationship_signal_events_kind",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_relationship_signal_events_confidence",
        ),
    )


class RelationshipSignalSourceORM(SQLModel, table=True):
    """Normalized raw-chat evidence for one relationship signal."""

    __tablename__ = "relationship_signal_sources"  # type: ignore[reportAssignmentType]

    signal_id: str = Field(
        sa_column=Column(
            String(64),
            ForeignKey("relationship_signal_events.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    chat_id: str = Field(
        sa_column=Column(
            String(26),
            ForeignKey("chats.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
            index=True,
        )
    )

    __table_args__ = (
        UniqueConstraint("signal_id", "chat_id", name="uq_relationship_signal_sources"),
    )
