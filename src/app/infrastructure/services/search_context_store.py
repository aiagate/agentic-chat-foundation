"""In-memory search workflow context store."""

from __future__ import annotations

from dataclasses import replace

from flow_res import Err, Ok, Result

from app.contracts.messages.retrieved_context import RetrievedContext
from app.contracts.ports.search_context_store import (
    ISearchContextStore,
    SearchContextStoreError,
)


class InMemorySearchContextStore(ISearchContextStore):
    """Keep retrieved context in memory for the current process."""

    def __init__(self) -> None:
        self._store: dict[str, RetrievedContext] = {}

    async def save(
        self,
        context: RetrievedContext,
    ) -> Result[None, SearchContextStoreError]:
        self._store[context.search_session_id] = context
        return Ok(None)

    async def get(
        self,
        search_session_id: str,
    ) -> Result[RetrievedContext, SearchContextStoreError]:
        context = self._store.get(search_session_id)
        if context is None:
            return Err(
                SearchContextStoreError(
                    f"Search context not found: {search_session_id}",
                )
            )
        return Ok(replace(context))
