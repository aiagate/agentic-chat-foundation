"""Memory semantic extraction port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.memory_semantic_extraction import (
    MemorySemanticExtractionRequest,
    MemorySemanticExtractionResult,
)


@dataclass
class MemorySemanticExtractionError(Exception):
    """Represents a semantic extraction failure."""

    message: str

    def __str__(self) -> str:
        return self.message


class IMemorySemanticExtractionService(ABC):
    """Interface for LLM-based memory semantic extraction."""

    @abstractmethod
    async def extract_memory_updates(
        self,
        request: MemorySemanticExtractionRequest,
    ) -> Result[MemorySemanticExtractionResult, MemorySemanticExtractionError]:
        """Extract durable memory patches from raw chat logs."""
        ...
