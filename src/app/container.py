"""Dependency injection container configuration."""

import os
from typing import cast

import injector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.conversation import (
    AIConversationResponseGenerator,
    SQLAlchemyConversationContext,
)
from app.bootstrap.character_selection import resolve_active_character_id
from app.contracts.ports.agent_inference_context import IAgentInferenceContextService
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.agent_turn_context_query import IAgentTurnContextQuery
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.conversation import (
    ConversationContext,
    ConversationHistory,
    ResponseGenerator,
)
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_index_projection import IMemoryIndexProjection
from app.contracts.ports.memory_index_query import IMemoryIndexQuery
from app.contracts.ports.memory_semantic_extraction import (
    IMemorySemanticExtractionService,
)
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.memory_write_service import IMemoryWriteService
from app.contracts.ports.tool_catalog import IToolCatalog
from app.contracts.ports.tool_executor import IToolExecutor
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.contracts.ports.web_search_service import IWebSearchService
from app.domain.queries.long_term_memory_query import ILongTermMemoryQuery
from app.infrastructure.memory.store import (
    FilesystemMemoryStore,
)
from app.infrastructure.orm_registry import init_orm_mappings
from app.infrastructure.queries.agent_turn_context_query import (
    SQLAlchemyAgentTurnContextQuery,
)
from app.infrastructure.queries.long_term_memory_query_service import (
    LongTermMemoryQueryService,
)
from app.infrastructure.queries.memory_index_projection_query import (
    SQLAlchemyMemoryIndexQuery,
)
from app.infrastructure.repositories.conversation_history import (
    SQLAlchemyConversationHistory,
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
    MemoryIndexProjectionService,
    MemorySemanticExtractionService,
    MockAIService,
    OllamaWebSearchService,
    StaticToolCatalog,
)
from app.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from app.presentation.conversation_flow import ConversationFlow


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
    def provide_conversation_history(self, uow: IUnitOfWork) -> ConversationHistory:
        """Provide the canonical raw conversation history adapter."""
        return SQLAlchemyConversationHistory(uow)

    @injector.provider
    def provide_agent_turn_context_query(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IAgentTurnContextQuery:
        """Provide the short-lived agent-turn read query."""
        return SQLAlchemyAgentTurnContextQuery(session_factory)


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
    def provide_memory_index_projection(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        character_id: str,
    ) -> IMemoryIndexProjection:
        """Provide the derived memory index projection synchronizer."""
        return MemoryIndexProjectionService(
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
        memory_index_projection: IMemoryIndexProjection,
    ) -> IMemoryConsolidationService:
        """Provide the memory consolidation orchestration service."""
        return MemoryConsolidationService(
            semantic_extraction_service=MemorySemanticExtractionService(
                ai_service,
                agent_profile_service,
            ),
            memory_index_projection=memory_index_projection,
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
    def provide_long_term_memory_query(self) -> ILongTermMemoryQuery:
        """Provide the query for pending long-term memory targets."""
        return LongTermMemoryQueryService()


class ApplicationModule(injector.Module):
    """Wire the four business use-case support services."""

    @injector.provider
    def provide_conversation_context(
        self,
        context_query: IAgentTurnContextQuery,
        character_id: str,
    ) -> ConversationContext:
        return SQLAlchemyConversationContext(context_query, character_id)

    @injector.provider
    def provide_response_generator(
        self,
        ai_service: IAIService,
        inference_context: IAgentInferenceContextService,
        tool_executor: IToolExecutor,
    ) -> ResponseGenerator:
        return AIConversationResponseGenerator(
            ai_service,
            inference_context,
            tool_executor,
        )

    @injector.provider
    def provide_conversation_flow(
        self,
        history: ConversationHistory,
        context: ConversationContext,
        generator: ResponseGenerator,
    ) -> ConversationFlow:
        return ConversationFlow(history, context, generator)


def configure(binder: injector.Binder) -> None:
    """Configure dependency injection bindings."""
    # Initialize ORM mappings
    init_orm_mappings()

    binder.install(DatabaseModule())
    binder.install(AIModule())
    binder.install(SearchModule())
    binder.install(MemoryModule())
    binder.install(ApplicationModule())
