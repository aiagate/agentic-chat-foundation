"""ORM model for chat rows processed by memory consolidation."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlmodel import Field, SQLModel


class MemoryConsolidatedChatSourceORM(SQLModel, table=True):
    """Derived projection identifying chat rows already folded into memory."""

    __tablename__ = "memory_consolidated_chat_sources"  # type: ignore[reportAssignmentType]

    chat_id: str = Field(
        sa_column=Column(
            String(26),
            ForeignKey("chats.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    consolidated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
