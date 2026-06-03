"""ORM model for the memory index projection table."""

from __future__ import annotations

from sqlalchemy import JSON, Column, Float, Text
from sqlmodel import Field, SQLModel


class MemoryIndexDocumentORM(SQLModel, table=True):
    """ORM model for `memory_index_documents`."""

    __tablename__ = "memory_index_documents"  # type: ignore[reportAssignmentType]

    source_path: str = Field(primary_key=True, max_length=512)
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
