"""Dependency injection container configuration."""

import os
from typing import cast

import injector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_index import IMemoryIndex
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.search_context_store import ISearchContextStore
from app.contracts.ports.web_search_service import IWebSearchService
from app.domain.repositories import IUnitOfWork
from app.infrastructure.messaging.in_memory_event_bus import InMemoryEventBus
from app.infrastructure.messaging.postgres_event_bus import PostgresEventBus
from app.infrastructure.messaging.redis_event_bus import RedisEventBus
from app.infrastructure.orm_registry import init_orm_mappings
from app.infrastructure.services import (
    DeterministicMemoryConsolidationService,
    FilesystemMemoryIndex,
    FilesystemMemoryService,
    GeminiService,
    GptService,
    InMemorySearchContextStore,
    MockAIService,
    OllamaWebSearchService,
)
from app.infrastructure.services.memory_store import FilesystemMemoryStore
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
    def provide_search_context_store(self) -> ISearchContextStore:
        """Provide the short-lived in-memory search context store."""
        return InMemorySearchContextStore()

    @injector.provider
    @injector.singleton
    def provide_web_search_service(self) -> IWebSearchService:
        """Provide the Ollama-backed web search service."""
        return OllamaWebSearchService()


class MemoryModule(injector.Module):
    """Module for memory service dependencies."""

    @injector.provider
    @injector.singleton
    def provide_memory_store(self) -> IMemoryStore:
        """Provide the filesystem-backed memory store."""
        from app.infrastructure.services.memory_store import default_memory_root

        return FilesystemMemoryStore(default_memory_root())

    @injector.provider
    @injector.singleton
    def provide_memory_index(self) -> IMemoryIndex:
        """Provide the persistent filesystem-backed memory index."""
        return FilesystemMemoryIndex()

    @injector.provider
    @injector.singleton
    def provide_memory_consolidation_service(
        self,
    ) -> IMemoryConsolidationService:
        """Provide the deterministic memory consolidation service."""
        return DeterministicMemoryConsolidationService()

    @injector.provider
    @injector.singleton
    def provide_memory_service(
        self,
        memory_store: IMemoryStore,
    ) -> IMemoryService:
        """Provide the filesystem-backed memory service."""
        return FilesystemMemoryService(
            store=cast(FilesystemMemoryStore, memory_store),
        )


def configure(binder: injector.Binder) -> None:
    """Configure dependency injection bindings."""
    # Initialize ORM mappings
    init_orm_mappings()

    binder.install(DatabaseModule())
    binder.install(MessagingModule())
    binder.install(AIModule())
    binder.install(SearchModule())
    binder.install(MemoryModule())
