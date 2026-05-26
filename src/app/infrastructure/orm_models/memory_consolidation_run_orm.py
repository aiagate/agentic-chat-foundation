"""ORM model for memory consolidation runs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Column, Date, DateTime
from sqlmodel import Field, SQLModel
from ulid import ULID


class MemoryConsolidationRunORM(SQLModel, table=True):
    """ORM model for memory_consolidation_runs table."""

    __tablename__ = "memory_consolidation_runs"  # type: ignore[reportAssignmentType]

    id: str | None = Field(
        default_factory=lambda: str(ULID()),
        primary_key=True,
        max_length=26,
    )
    run_key: str = Field(max_length=255, unique=True)
    job_name: str = Field(max_length=100, index=True)
    target_date: date | None = Field(default=None, sa_column=Column(Date, index=True))
    status: str = Field(default="pending", max_length=50, index=True)
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    result_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
