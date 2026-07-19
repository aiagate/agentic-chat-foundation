"""Dependency injection container configuration."""

import os
from typing import cast

import injector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.conversation import (
    AIConversationResponseGenerator,
    ConversationContextService,
)
from app.application.discussion import (
    LocalAutonomousTopicGuard,
    LocalAutonomousTopicGuardSettings,
    LocalSpeechGuard,
    LocalSpeechGuardSettings,
    StructuredAgentTurnEvaluator,
    StructuredAutonomousTopicEvaluator,
)
from app.application.relationship import RelationshipInteractionProcessor
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
from app.contracts.ports.discussion import (
    IAgentTurnEvaluator,
    IAutonomousTopicEvaluator,
    IAutonomousTopicGuard,
    IAutonomousTopicRepository,
    IDiscussionRepository,
    ILocalSpeechGuard,
)
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_index_projection import IMemoryIndexProjection
from app.contracts.ports.memory_index_query import IMemoryIndexQuery
from app.contracts.ports.memory_semantic_extraction import (
    IMemorySemanticExtractionService,
)
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.relationship import (
    IRelationshipInteractionProcessor,
    IRelationshipQuery,
    IRelationshipSignalEvaluator,
)
from app.contracts.ports.tool_catalog import IToolCatalog
from app.contracts.ports.tool_executor import IToolExecutor
from app.contracts.ports.unit_of_work import IUnitOfWorkFactory
from app.contracts.ports.user_identity_query import IUserIdentityQuery
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
from app.infrastructure.queries.relationship_query import SQLAlchemyRelationshipQuery
from app.infrastructure.queries.user_identity_query import SQLAlchemyUserIdentityQuery
from app.infrastructure.repositories.conversation_history import (
    SQLAlchemyConversationHistory,
)
from app.infrastructure.repositories.discussion_repository import (
    SQLAlchemyDiscussionRepository,
)
from app.infrastructure.services import (
    AgentInferenceContextService,
    FilesystemAgentProfileService,
    FilesystemMemoryService,
    GeminiEmbeddingService,
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
from app.infrastructure.services.relationship_signal_evaluator import (
    LLMRelationshipSignalEvaluator,
)
from app.infrastructure.unit_of_work import (
    SQLAlchemyUnitOfWorkFactory,
)
from app.presentation.conversation_flow import ConversationFlow
from app.usecases.discussion.generate_autonomous_topic import (
    GenerateAutonomousTopicHandler,
)
from app.usecases.discussion.process_discussion_message import (
    ProcessDiscussionMessageHandler,
)


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
    @injector.singleton
    def provide_unit_of_work_factory(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IUnitOfWorkFactory:
        """Provide a factory so each request owns an independent UoW."""
        return SQLAlchemyUnitOfWorkFactory(session_factory)

    @injector.provider
    def provide_conversation_history(
        self,
        uow_factory: IUnitOfWorkFactory,
        character_id: str,
    ) -> ConversationHistory:
        """Provide the canonical raw conversation history adapter."""
        return SQLAlchemyConversationHistory(uow_factory, character_id)

    @injector.provider
    def provide_agent_turn_context_query(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IAgentTurnContextQuery:
        """Provide the short-lived agent-turn read query."""
        return SQLAlchemyAgentTurnContextQuery(session_factory)

    @injector.provider
    def provide_user_identity_query(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IUserIdentityQuery:
        """Provide canonical user lookup by external channel identity."""

        return SQLAlchemyUserIdentityQuery(session_factory)

    @injector.provider
    def provide_relationship_query(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IRelationshipQuery:
        return SQLAlchemyRelationshipQuery(session_factory)

    @injector.provider
    @injector.singleton
    def provide_relationship_signal_evaluator(
        self,
        ai_service: IAIService,
    ) -> IRelationshipSignalEvaluator:
        return LLMRelationshipSignalEvaluator(ai_service)

    @injector.provider
    def provide_relationship_interaction_processor(
        self,
        evaluator: IRelationshipSignalEvaluator,
        agent_profile_service: IAgentProfileService,
        uow_factory: IUnitOfWorkFactory,
    ) -> IRelationshipInteractionProcessor:
        return RelationshipInteractionProcessor(
            evaluator,
            agent_profile_service,
            uow_factory,
        )

    @injector.provider
    @injector.singleton
    def provide_discussion_repository(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IDiscussionRepository:
        return SQLAlchemyDiscussionRepository(session_factory)

    @injector.provider
    @injector.singleton
    def provide_autonomous_topic_repository(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> IAutonomousTopicRepository:
        return SQLAlchemyDiscussionRepository(session_factory)


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
    ) -> IMemoryIndexProjection:
        """Provide the derived memory index projection synchronizer."""
        return MemoryIndexProjectionService(
            session_factory=session_factory,
            embedding_service=GeminiEmbeddingService(),
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
        memory_store: IMemoryStore,
    ) -> IMemoryConsolidationService:
        """Provide the memory consolidation orchestration service."""
        return MemoryConsolidationService(
            store=memory_store,
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
    ) -> IMemoryService:
        """Provide memory retrieval through the persisted projection."""
        return FilesystemMemoryService(index_query=memory_index_query)

    @injector.provider
    def provide_agent_inference_context_service(
        self,
        memory_service: IMemoryService,
        agent_profile_service: IAgentProfileService,
        tool_catalog: IToolCatalog,
        relationship_query: IRelationshipQuery,
    ) -> IAgentInferenceContextService:
        """Provide prompt-ready agent inference context assembly."""
        return AgentInferenceContextService(
            memory_service,
            agent_profile_service,
            tool_catalog,
            relationship_query,
        )

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
        web_search_service: IWebSearchService,
    ) -> IToolExecutor:
        """Provide the generic tool executor adapter."""
        return GenericToolExecutor(
            memory_service=memory_service,
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
        return ConversationContextService(context_query, character_id)

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
        user_identity_query: IUserIdentityQuery,
        relationship_processor: IRelationshipInteractionProcessor,
    ) -> ConversationFlow:
        return ConversationFlow(
            history,
            context,
            generator,
            user_identity_query,
            relationship_processor,
        )

    @injector.provider
    def provide_agent_turn_evaluator(
        self,
        ai_service: IAIService,
        agent_profile_service: IAgentProfileService,
    ) -> IAgentTurnEvaluator:
        return StructuredAgentTurnEvaluator(ai_service, agent_profile_service)

    @injector.provider
    def provide_autonomous_topic_evaluator(
        self,
        ai_service: IAIService,
        agent_profile_service: IAgentProfileService,
    ) -> IAutonomousTopicEvaluator:
        return StructuredAutonomousTopicEvaluator(ai_service, agent_profile_service)

    @injector.provider
    @injector.singleton
    def provide_local_speech_guard(self) -> ILocalSpeechGuard:
        return LocalSpeechGuard(
            LocalSpeechGuardSettings(
                max_consecutive_bot_messages=_positive_int_env(
                    "DISCORD_MAX_CONSECUTIVE_BOT_MESSAGES", 8
                ),
                cooldown_seconds=_positive_int_env(
                    "DISCORD_SPEAK_COOLDOWN_SECONDS", 20
                ),
                rate_window_seconds=_positive_int_env(
                    "DISCORD_RATE_WINDOW_SECONDS", 300
                ),
                max_published_turns_per_window=_positive_int_env(
                    "DISCORD_MAX_PUBLISHED_TURNS_PER_WINDOW", 5
                ),
            )
        )

    @injector.provider
    def provide_process_discussion_message_handler(
        self,
        repository: IDiscussionRepository,
        evaluator: IAgentTurnEvaluator,
        speech_guard: ILocalSpeechGuard,
    ) -> ProcessDiscussionMessageHandler:
        return ProcessDiscussionMessageHandler(repository, evaluator, speech_guard)

    @injector.provider
    @injector.singleton
    def provide_autonomous_topic_guard(self) -> IAutonomousTopicGuard:
        return LocalAutonomousTopicGuard(
            LocalAutonomousTopicGuardSettings(
                idle_seconds=_positive_int_env(
                    "DISCORD_AUTONOMOUS_TOPIC_IDLE_SECONDS", 1800
                ),
                minimum_evaluation_interval_seconds=_positive_int_env(
                    "DISCORD_AUTONOMOUS_TOPIC_EVALUATION_COOLDOWN_SECONDS", 900
                ),
                rate_window_seconds=_positive_int_env(
                    "DISCORD_AUTONOMOUS_TOPIC_RATE_WINDOW_SECONDS", 86400
                ),
                max_published_topics_per_window=_positive_int_env(
                    "DISCORD_AUTONOMOUS_TOPIC_MAX_PUBLISHED_PER_WINDOW", 3
                ),
            )
        )

    @injector.provider
    def provide_generate_autonomous_topic_handler(
        self,
        discussion_repository: IDiscussionRepository,
        topic_repository: IAutonomousTopicRepository,
        evaluator: IAutonomousTopicEvaluator,
        guard: IAutonomousTopicGuard,
    ) -> GenerateAutonomousTopicHandler:
        return GenerateAutonomousTopicHandler(
            discussion_repository,
            topic_repository,
            evaluator,
            guard,
        )


def configure(binder: injector.Binder) -> None:
    """Configure dependency injection bindings."""
    # Initialize ORM mappings
    init_orm_mappings()

    binder.install(DatabaseModule())
    binder.install(AIModule())
    binder.install(SearchModule())
    binder.install(MemoryModule())
    binder.install(ApplicationModule())


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default
