"""Tests for infrastructure database component."""

import pytest
from sqlalchemy import text

from app.infrastructure.database import get_session


@pytest.mark.anyio
async def test_get_db_session(test_db_engine: None) -> None:
    """Test get_session provides a valid session."""
    session_generator = get_session()
    session = await anext(session_generator)
    try:
        assert session is not None
        # Perform a simple query to ensure the session is active
        await session.execute(text("SELECT 1"))
    finally:
        await session.close()
        await session_generator.aclose()
