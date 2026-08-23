"""Pytest configuration and fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.contracts.ports.unit_of_work import IUnitOfWork
from app.infrastructure.orm_registry import init_orm_mappings
from app.infrastructure.unit_of_work import SQLAlchemyUnitOfWork

# Initialize ORM mappings before any tests
init_orm_mappings()


@pytest.fixture(scope="function")
async def test_db_engine() -> AsyncGenerator[None]:
    """Create test database engine with in-memory SQLite."""
    test_url = "sqlite+aiosqlite:///:memory:"

    engine = create_async_engine(test_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    from app.infrastructure import database

    old_engine = database._engine
    old_session_factory = database._session_factory

    database._engine = engine
    database._session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    yield

    database._engine = old_engine
    database._session_factory = old_session_factory
    await engine.dispose()


@pytest.fixture(scope="function")
async def session_factory(
    test_db_engine: None,
) -> async_sessionmaker[AsyncSession]:
    """Provide session factory for tests."""
    from app.infrastructure import database

    if database._session_factory is None:
        raise RuntimeError("Database not initialized")
    return database._session_factory


@pytest.fixture(scope="function")
def anyio_backend() -> str:
    """Specify anyio backend for pytest-anyio."""
    return "asyncio"


def pytest_configure(config: pytest.Config) -> None:
    """Register custom test markers."""

    config.addinivalue_line(
        "markers",
        (
            "scenario: live external-service scenario tests that are skipped "
            "unless RUN_SCENARIO_TESTS=1"
        ),
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip live scenario tests unless they are explicitly enabled."""

    del config
    if os.getenv("RUN_SCENARIO_TESTS") == "1":
        return

    skip_marker = pytest.mark.skip(
        reason=(
            "Scenario tests require RUN_SCENARIO_TESTS=1 and a configured live AI "
            "provider."
        )
    )
    for item in items:
        if item.get_closest_marker("scenario") is not None:
            item.add_marker(skip_marker)


@pytest.fixture
async def uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> IUnitOfWork:
    """Provide Unit of Work for tests."""
    return SQLAlchemyUnitOfWork(session_factory)
