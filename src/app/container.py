"""Dependency injection container configuration."""

import os
from typing import cast

import injector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.character_definition import selected_character_definition
from app.contracts.messages.memory_index import (
    MemoryIndexDocument,
    MemorySearchFilters,
    MemorySearchResult,
)
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_index import IMemoryIndex
from app.contracts.ports.memory_index_maintenance import IMemoryIndexMaintenance
from app.contracts.ports.memory_semantic_extraction import (
    IMemorySemanticExtractionService,
)
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.memory_write_service import IMemoryWriteService
from app.contracts.ports.retrieved_context_store import IRetrievedContextStore
from app.contracts.ports.tool_call_store import IToolCallStore
from app.contracts.ports.tool_catalog import IToolCatalog
from app.contracts.ports.tool_execution_lock import IToolExecutionLock
from app.contracts.ports.tool_executor import IToolExecutor
from app.contracts.ports.web_search_service import IWebSearchService
from app.domain.repositories import IUnitOfWork
from app.infrastructure.memory.embedding import GeminiEmbeddingService
from app.infrastructure.memory.store import (
    FilesystemMemoryStore,
    StoredMemoryDocument,
)
from app.infrastructure.messaging.in_memory_event_bus import InMemoryEventBus
from app.infrastructure.messaging.postgres_event_bus import PostgresEventBus
from app.infrastructure.messaging.redis_event_bus import RedisEventBus
from app.infrastructure.orm_registry import init_orm_mappings
from app.infrastructure.queries.memory_sleep_query_service import (
    MemorySleepQueryService,
)
from app.infrastructure.services import (
    FilesystemAgentProfileService,
    FilesystemMemoryIndex,
    FilesystemMemoryService,
    FilesystemMemoryWriteService,
    GeminiService,
    GenericToolExecutor,
    GptService,
    MemoryConsolidationService,
    MemoryIndexMaintenanceService,
    MemorySemanticExtractionService,
    MockAIService,
    OllamaWebSearchService,
    StaticToolCatalog,
)
from app.infrastructure.stores.retrieved_context_store import (
    InMemoryRetrievedContextStore,
    RedisRetrievedContextStore,
)
from app.infrastructure.stores.tool_call_store import (
    InMemoryToolCallStore,
    RedisToolCallStore,
)
from app.infrastructure.stores.tool_execution_lock import (
    InMemoryToolExecutionLock,
    RedisToolExecutionLock,
)
from app.infrastructure.unit_of_work import SQLAlchemyUnitOfWork


class DatabaseModule(injector.Module):
    """Module for database-related dependencies."""

    @injector.provider
    def provide_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Provide session factory for creating database sessions."""
        from app.infrastructure import database

        if database._session_factory is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        return database._session_factory

    @injector.provider
    def provide_unit_of_work(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IUnitOfWork:
        """Provide Unit of Work implementation for transaction management."""
        return SQLAlchemyUnitOfWork(session_factory)


class MessagingModule(injector.Module):
    """Module for messaging-related dependencies."""

    @injector.provider
    @injector.singleton
    def provide_event_bus(self) -> IEventBus:
        """Provide Event Bus implementation."""
        provider = os.getenv("EVENT_BUS_PROVIDER")
        if provider is None:
            if os.getenv("REDIS_URL"):
                provider = "redis"
            elif os.getenv("DATABASE_URL", "").startswith("postgresql"):
                provider = "postgres"
            else:
                provider = "memory"

        provider = provider.lower()
        match provider:
            case "redis":
                return RedisEventBus()
            case "postgres":
                return PostgresEventBus()
            case _:
                return InMemoryEventBus()


class AIModule(injector.Module):
    """Module for AI service dependencies."""

    @injector.provider
    @injector.singleton
    def provide_ai_service(self) -> IAIService:
        """Provide AI service based on environment variable."""
        provider = os.getenv("AI_PROVIDER", "mock").lower()
        match provider:
            case "gemini":
                return GeminiService()
            case "gpt" | "openai":
                return GptService()
            case _:
                return MockAIService()


class SearchModule(injector.Module):
    """Module for search workflow dependencies."""

    @injector.provider
    @injector.singleton
    def provide_retrieved_context_store(self) -> IRetrievedContextStore:
        """Provide the short-lived in-memory retrieved context store."""
        if os.getenv("REDIS_URL"):
            return RedisRetrievedContextStore()
        return InMemoryRetrievedContextStore()

    @injector.provider
    @injector.singleton
    def provide_tool_call_store(self) -> IToolCallStore:
        """Provide the short-lived tool call store."""
        if os.getenv("REDIS_URL"):
            return RedisToolCallStore()
        return InMemoryToolCallStore()

    @injector.provider
    @injector.singleton
    def provide_tool_execution_lock(self) -> IToolExecutionLock:
        """Provide the short-lived tool execution idempotency lock."""
        if os.getenv("REDIS_URL"):
            return RedisToolExecutionLock()
        return InMemoryToolExecutionLock()

    @injector.provider
    @injector.singleton
    def provide_web_search_service(self) -> IWebSearchService:
        """Provide the Ollama-backed web search service."""
        return OllamaWebSearchService()


class MemoryModule(injector.Module):
    """Module for memory service dependencies."""

    @injector.provider
    @injector.singleton
    def provide_agent_profile_service(
        self,
        memory_store: IMemoryStore,
    ) -> IAgentProfileService:
        """Provide the filesystem-backed agent profile bundle service."""
        filesystem_store = cast(FilesystemMemoryStore, memory_store)
        character = selected_character_definition()
        service = FilesystemAgentProfileService(
            store=filesystem_store,
            character=character,
        )
        service.ensure_agent_profile_bundle()
        return service

    @injector.provider
    @injector.singleton
    def provide_memory_store(self) -> IMemoryStore:
        """Provide the filesystem-backed memory store."""
        from app.infrastructure.memory.store import default_memory_root

        return FilesystemMemoryStore(default_memory_root())

    @injector.provider
    @injector.singleton
    def provide_memory_index(
        self,
    ) -> IMemoryIndex[
        StoredMemoryDocument,
        MemoryIndexDocument,
        MemorySearchResult,
        MemorySearchFilters,
    ]:
        """Provide the persistent filesystem-backed memory index."""
        return FilesystemMemoryIndex(embedding_service=GeminiEmbeddingService())

    @injector.provider
    @injector.singleton
    def provide_memory_index_maintenance(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IMemoryIndexMaintenance:
        """Provide the memory index maintenance service."""
        return MemoryIndexMaintenanceService(
            session_factory=session_factory,
            embedding_service=GeminiEmbeddingService(),
        )

    @injector.provider
    @injector.singleton
    def provide_memory_consolidation_service(
        self,
        ai_service: IAIService,
        agent_profile_service: IAgentProfileService,
        memory_index_maintenance: IMemoryIndexMaintenance,
    ) -> IMemoryConsolidationService:
        """Provide the memory consolidation orchestration service."""
        return MemoryConsolidationService(
            semantic_extraction_service=MemorySemanticExtractionService(
                ai_service,
                agent_profile_service,
            ),
            memory_index_maintenance=memory_index_maintenance,
            agent_profile_service=agent_profile_service,
        )

    @injector.provider
    @injector.singleton
    def provide_memory_semantic_extraction_service(
        self,
        ai_service: IAIService,
        agent_profile_service: IAgentProfileService,
    ) -> IMemorySemanticExtractionService:
        """Provide the LLM-backed memory semantic extraction service."""
        return MemorySemanticExtractionService(ai_service, agent_profile_service)

    @injector.provider
    @injector.singleton
    def provide_memory_service(
        self,
        memory_store: IMemoryStore,
        agent_profile_service: IAgentProfileService,
    ) -> IMemoryService:
        """Provide the filesystem-backed memory service."""
        filesystem_store = cast(FilesystemMemoryStore, memory_store)
        character = selected_character_definition()
        return FilesystemMemoryService(
            store=filesystem_store,
            embedding_service=GeminiEmbeddingService(),
            agent_profile_service=agent_profile_service,
            character=character,
        )

    @injector.provider
    @injector.singleton
    def provide_memory_write_service(
        self,
        memory_store: IMemoryStore,
    ) -> IMemoryWriteService:
        """Provide the filesystem-backed memory write service."""
        filesystem_store = cast(FilesystemMemoryStore, memory_store)
        return FilesystemMemoryWriteService(store=filesystem_store)

    @injector.provider
    @injector.singleton
    def provide_tool_catalog(self) -> IToolCatalog:
        """Provide the static agent tool catalog."""
        return StaticToolCatalog()

    @injector.provider
    @injector.singleton
    def provide_tool_executor(
        self,
        event_bus: IEventBus,
        retrieved_context_store: IRetrievedContextStore,
        memory_service: IMemoryService,
        memory_write_service: IMemoryWriteService,
    ) -> IToolExecutor:
        """Provide the generic tool executor adapter."""
        return GenericToolExecutor(
            event_bus=event_bus,
            retrieved_context_store=retrieved_context_store,
            memory_service=memory_service,
            memory_write_service=memory_write_service,
        )

    @injector.provider
    @injector.singleton
    def provide_memory_sleep_query_service(self) -> MemorySleepQueryService:
        """Provide the query service for pending memory sleep targets."""
        return MemorySleepQueryService()


def configure(binder: injector.Binder) -> None:
    """Configure dependency injection bindings."""
    # Initialize ORM mappings
    init_orm_mappings()

    binder.install(DatabaseModule())
    binder.install(MessagingModule())
    binder.install(AIModule())
    binder.install(SearchModule())
    binder.install(MemoryModule())
