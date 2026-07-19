"""Database configuration and session management."""

import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Engine will be initialized from settings
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _json_serializer(obj: Any) -> str:
    """Serialize JSON values without ASCII escaping."""

    return json.dumps(obj, ensure_ascii=False)


def sqlalchemy_echo_enabled() -> bool:
    """Return whether SQLAlchemy statement logging was explicitly enabled."""

    return os.getenv("SQLALCHEMY_ECHO", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def init_db(database_url: str, **engine_kwargs: Any) -> None:
    """Initialize database engine and session factory."""
    global _engine, _session_factory
    if "json_serializer" not in engine_kwargs:
        engine_kwargs["json_serializer"] = _json_serializer
    _engine = create_async_engine(database_url, **engine_kwargs)
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_engine() -> AsyncEngine:
    """Get the global database engine."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


def get_sqlite_database_path() -> Path | None:
    """Return the configured SQLite database file path, if any."""

    if _engine is None:
        return None
    url = _engine.url
    if not url.drivername.startswith("sqlite"):
        return None
    database = url.database
    if database is None or database in {":memory:", ""}:
        return None
    return Path(database)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Get database session for dependency injection."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with _session_factory() as session:
        yield session
