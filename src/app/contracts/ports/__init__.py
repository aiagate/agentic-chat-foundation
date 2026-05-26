"""Application ports."""

from app.contracts.ports.ai_service import AIServiceError, IAIService
from app.contracts.ports.embedding_service import (
    EmbeddingServiceError,
    IEmbeddingService,
)
from app.contracts.ports.event_bus import EventHandler, IEventBus
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_index import IMemoryIndex, MemoryIndexError
from app.contracts.ports.memory_service import IMemoryService, MemoryServiceError
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.search_context_store import (
    ISearchContextStore,
    SearchContextStoreError,
)
from app.contracts.ports.web_search_service import (
    IWebSearchService,
    WebSearchServiceError,
)

__all__ = [
    "AIServiceError",
    "EmbeddingServiceError",
    "EventHandler",
    "IAIService",
    "IEmbeddingService",
    "IEventBus",
    "IMemoryConsolidationService",
    "IMemoryIndex",
    "IMemoryService",
    "IMemoryStore",
    "ISearchContextStore",
    "MemoryIndexError",
    "MemoryServiceError",
    "SearchContextStoreError",
    "IWebSearchService",
    "WebSearchServiceError",
]
