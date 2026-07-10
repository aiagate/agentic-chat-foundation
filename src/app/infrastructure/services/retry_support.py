"""Retry helpers for external service calls."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable


async def call_with_exponential_backoff[T](
    operation: Callable[[], Awaitable[T]],
    *,
    service_name: str,
    logger: logging.Logger,
    max_attempts: int = 5,
    initial_delay_seconds: float = 1.0,
    max_delay_seconds: float = 8.0,
    backoff_multiplier: float = 2.0,
) -> T:
    """Run an external call with exponential backoff between retries."""

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except Exception as error:
            last_error = error
            if attempt >= max_attempts:
                raise

            delay_seconds = min(
                initial_delay_seconds * (backoff_multiplier ** (attempt - 1)),
                max_delay_seconds,
            )
            logger.warning(
                "%s API call failed; retrying in %.1fs (%s/%s): %s",
                service_name,
                delay_seconds,
                attempt,
                max_attempts - 1,
                error,
            )
            await asyncio.sleep(delay_seconds)

    assert last_error is not None
    raise last_error
