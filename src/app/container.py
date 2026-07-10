"""Dependency injection container configuration."""

import os
from typing import cast

import injector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.agent import (
    AgentReplyPersistence,
    AgentRunCoordinator,
    AgentToolCoordinator,
    AgentTurnRunner,
)
from app.bootstrap.character_selection import resolve_active_character_id
from app.contracts.ports.agent_inference_context import IAgentInferenceContextService
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.agent_turn_context_query import IAgentTurnContextQuery
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_index_maintenance import IMemoryIndexMaintenance
from app.contracts.ports.memory_index_query import IMemoryIndexQuery
from app.contracts.ports.memory_semantic_extraction import (
    IMemorySemanticExtractionService,
)
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.memory_write_service import IMemoryWriteService
from app.contracts.ports.outbox_store import IOutboxStore
from app.contracts.ports.tool_catalog import IToolCatalog
from app.contracts.ports.tool_executor import IToolExecutor
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.contracts.ports.web_search_service import IWebSearchService
from app.domain.queries.memory_sleep_query import IMemorySleepQuery
from app.infrastructure.memory.store import (
    FilesystemMemoryStore,
)
from app.infrastructure.messaging.in_memory_event_bus import InMemoryEventBus
from app.infrastructure.messaging.redis_event_bus import RedisEventBus
from app.infrastructure.orm_registry import init_orm_mappings
from app.infrastructure.queries.agent_turn_context_query import (
    SQLAlchemyAgentTurnContextQuery,
)
from app.infrastructure.queries.memory_index_projection_query import (
    SQLAlchemyMemoryIndexQuery,
)
from app.infrastructure.queries.memory_sleep_query_service import (
    MemorySleepQueryService,
)
from app.infrastructure.services import (
    AgentInferenceContextService,
    FilesystemAgentProfileService,
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
from app.infrastructure.stores.outbox_store import SQLAlchemyOutboxStore
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

    @injector.provider
    def provide_agent_turn_context_query(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IAgentTurnContextQuery:
        """Provide the short-lived agent-turn read query."""
        return SQLAlchemyAgentTurnContextQuery(session_factory)

    @injector.provider
    def provide_outbox_store(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IOutboxStore:
        """Provide the durable outbox delivery store."""
        return SQLAlchemyOutboxStore(session_factory)


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
            else:
                provider = "memory"

        provider = provider.lower()
        match provider:
            case "redis":
                return RedisEventBus()
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
    def provide_web_search_service(self) -> IWebSearchService:
        """Provide the Ollama-backed web search service."""
        return OllamaWebSearchService()


class MemoryModule(injector.Module):
    """Module for memory service dependencies."""

    @injector.provider
    @injector.singleton
    def provide_character_id(self) -> str:
        """Provide the active character identifier for this process."""
        return resolve_active_character_id()

    @injector.provider
    @injector.singleton
    def provide_agent_profile_service(
        self,
        memory_store: IMemoryStore,
        character_id: str,
    ) -> IAgentProfileService:
        """Provide the filesystem-backed agent profile bundle service."""
        filesystem_store = cast(FilesystemMemoryStore, memory_store)
        service = FilesystemAgentProfileService(
            store=filesystem_store,
            character_id=character_id,
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
    def provide_memory_index_maintenance(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        character_id: str,
    ) -> IMemoryIndexMaintenance:
        """Provide the memory index maintenance service."""
        return MemoryIndexMaintenanceService(
            session_factory=session_factory,
            character_id=character_id,
        )

    @injector.provider
    def provide_memory_index_query(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        memory_store: IMemoryStore,
    ) -> IMemoryIndexQuery:
        """Provide the main-database-backed memory projection query."""

        return SQLAlchemyMemoryIndexQuery(
            session_factory,
            cast(FilesystemMemoryStore, memory_store),
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
        memory_index_query: IMemoryIndexQuery,
        agent_profile_service: IAgentProfileService,
        character_id: str,
    ) -> IMemoryService:
        """Provide memory retrieval through the persisted projection."""
        return FilesystemMemoryService(
            index_query=memory_index_query,
            agent_profile_service=agent_profile_service,
            character_id=character_id,
        )

    @injector.provider
    def provide_agent_inference_context_service(
        self,
        memory_service: IMemoryService,
        agent_profile_service: IAgentProfileService,
        tool_catalog: IToolCatalog,
    ) -> IAgentInferenceContextService:
        """Provide prompt-ready agent inference context assembly."""
        return AgentInferenceContextService(
            memory_service,
            agent_profile_service,
            tool_catalog,
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
        memory_service: IMemoryService,
        memory_write_service: IMemoryWriteService,
        web_search_service: IWebSearchService,
    ) -> IToolExecutor:
        """Provide the generic tool executor adapter."""
        return GenericToolExecutor(
            memory_service=memory_service,
            memory_write_service=memory_write_service,
            web_search_service=web_search_service,
        )

    @injector.provider
    @injector.singleton
    def provide_memory_sleep_query_service(self) -> IMemorySleepQuery:
        """Provide the query service for pending memory sleep targets."""
        return MemorySleepQueryService()


class ApplicationModule(injector.Module):
    """Wire durable application orchestration components."""

    @injector.provider
    def provide_agent_turn_runner(
        self,
        ai_service: IAIService,
        context_query: IAgentTurnContextQuery,
        inference_context: IAgentInferenceContextService,
    ) -> AgentTurnRunner:
        return AgentTurnRunner(ai_service, context_query, inference_context)

    @injector.provider
    def provide_agent_run_coordinator(
        self,
        uow: IUnitOfWork,
        turn_runner: AgentTurnRunner,
        tool_catalog: IToolCatalog,
        reply_persistence: AgentReplyPersistence,
    ) -> AgentRunCoordinator:
        return AgentRunCoordinator(uow, turn_runner, tool_catalog, reply_persistence)

    @injector.provider
    def provide_agent_tool_coordinator(
        self,
        uow: IUnitOfWork,
        tool_executor: IToolExecutor,
        reply_persistence: AgentReplyPersistence,
    ) -> AgentToolCoordinator:
        return AgentToolCoordinator(uow, tool_executor, reply_persistence)

    @injector.provider
    def provide_agent_reply_persistence(
        self, uow: IUnitOfWork
    ) -> AgentReplyPersistence:
        return AgentReplyPersistence(uow)


def configure(binder: injector.Binder) -> None:
    """Configure dependency injection bindings."""
    # Initialize ORM mappings
    init_orm_mappings()

    binder.install(DatabaseModule())
    binder.install(MessagingModule())
    binder.install(AIModule())
    binder.install(SearchModule())
    binder.install(MemoryModule())
    binder.install(ApplicationModule())
