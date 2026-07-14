"""Ensure the active SQLModel tables are imported before database setup."""

from app.infrastructure.orm_models.chat_orm import ChatORM
from app.infrastructure.orm_models.memory_consolidated_chat_source_orm import (
    MemoryConsolidatedChatSourceORM,
)
from app.infrastructure.orm_models.memory_index_orm import MemoryIndexDocumentORM


def init_orm_mappings() -> None:
    """Import active projection models so SQLModel metadata is complete."""
    # Import-only projection models must remain registered in SQLModel metadata.
    _ = (
        ChatORM,
        MemoryConsolidatedChatSourceORM,
        MemoryIndexDocumentORM,
    )
