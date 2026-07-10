"""ORM model for backed up memory index projection rows."""

from __future__ import annotations

from sqlalchemy import JSON, Column, Float, Text
from sqlmodel import Field, SQLModel


class MemoryIndexBackupORM(SQLModel, table=True):
    """ORM model for `memory_index_document_backups`."""

    __tablename__ = "memory_index_document_backups"  # type: ignore[reportAssignmentType]

    scope_user_id: str = Field(max_length=255, primary_key=True, index=True)
    source_path: str = Field(primary_key=True, max_length=512)
    backed_up_at: str = Field(max_length=64, index=True)
    user_id: str | None = Field(default=None, max_length=255, index=True)
    memory_type: str = Field(max_length=32, index=True)
    source_id: str = Field(max_length=255, index=True)
    title: str | None = Field(default=None, max_length=255)
    content_hash: str = Field(max_length=64, index=True)
    indexed_text: str = Field(sa_column=Column(Text, nullable=False))
    tags_json: str = Field(sa_column=Column(Text, nullable=False))
    status: str | None = Field(default=None, max_length=50, index=True)
    timeline_type: str | None = Field(default=None, max_length=50, index=True)
    occurred_at: str | None = Field(default=None, max_length=64, index=True)
    updated_at: str = Field(max_length=64, index=True)
    importance: float = Field(sa_column=Column(Float, nullable=False))
    confidence: float = Field(sa_column=Column(Float, nullable=False))
    decay_score: float = Field(sa_column=Column(Float, nullable=False))
    embedding: list[float] = Field(sa_column=Column(JSON, nullable=False))
