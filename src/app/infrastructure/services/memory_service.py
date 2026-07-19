"""Filesystem-backed memory service for the app layer."""

from __future__ import annotations

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.memory_context import (
    MemoryContextPack,
    MemoryEntity,
    MemoryProfile,
    MemoryReadResult,
    MemoryTimelineEntry,
)
from app.contracts.messages.memory_index import MemoryIndexDocument
from app.contracts.ports.memory_index_query import IMemoryIndexQuery
from app.contracts.ports.memory_service import IMemoryService, MemoryServiceError
from app.infrastructure.memory.context_formatter import (
    manifest_item_from_document,
    memory_read_result_from_document,
    render_manifest_context,
)
from app.infrastructure.memory.context_loader import (
    entity_from_document,
    profile_from_document,
    timeline_from_document,
)
from app.infrastructure.memory.markdown import MemoryMarkdownError
from app.infrastructure.memory.store import MemoryStoreError


class FilesystemMemoryService(IMemoryService):
    """Adapter that retrieves memory from the local filesystem."""

    def __init__(
        self,
        index_query: IMemoryIndexQuery,
    ) -> None:
        self._index_query = index_query

    async def build_context(
        self,
        user_id: str,
    ) -> Result[MemoryContextPack, MemoryServiceError]:
        """Return a prompt-ready compact manifest for the user scope."""

        try:
            documents_result = await self._index_query.list_documents(
                user_id=user_id,
            )
            if is_err(documents_result):
                return Err(MemoryServiceError(str(documents_result.error)))
            index_documents = documents_result.value
            manifest_items = [
                manifest_item_from_document(document) for document in index_documents
            ]
            return Ok(
                MemoryContextPack(
                    user_id=user_id,
                    assembled_context=render_manifest_context(manifest_items),
                    manifest_items=manifest_items,
                    profile=_user_profile(index_documents, user_id=user_id),
                    timelines=_timelines(index_documents),
                    entities=_entities(index_documents),
                )
            )
        except (MemoryMarkdownError, MemoryStoreError, OSError, ValueError) as exc:
            return Err(MemoryServiceError(str(exc)))

    async def read_memory(
        self,
        memory_id: str,
        user_id: str,
    ) -> Result[MemoryReadResult, MemoryServiceError]:
        """Resolve one detailed memory payload addressed by memory_id."""

        try:
            documents_result = await self._index_query.list_documents(
                user_id=user_id,
            )
            if is_err(documents_result):
                return Err(MemoryServiceError(str(documents_result.error)))
            index_documents = documents_result.value
            for document in index_documents:
                manifest_item = manifest_item_from_document(document)
                if manifest_item.memory_id != memory_id:
                    continue
                return Ok(memory_read_result_from_document(document, manifest_item))
            return Err(MemoryServiceError(f"Memory not found: {memory_id}"))
        except (MemoryMarkdownError, MemoryStoreError, OSError, ValueError) as exc:
            return Err(MemoryServiceError(str(exc)))


def _user_profile(
    documents: list[MemoryIndexDocument],
    *,
    user_id: str,
) -> MemoryProfile | None:
    for document in documents:
        front_matter = document.document.front_matter
        if (
            front_matter.get("memory_type") == "profile"
            and front_matter.get("user_id") == user_id
        ):
            return profile_from_document(document.document)
    return None


def _timelines(documents: list[MemoryIndexDocument]) -> list[MemoryTimelineEntry]:
    return [
        timeline_from_document(document.document)
        for document in documents
        if document.document.front_matter.get("memory_type") == "timeline"
    ]


def _entities(documents: list[MemoryIndexDocument]) -> list[MemoryEntity]:
    return [
        entity_from_document(document.document)
        for document in documents
        if document.document.front_matter.get("memory_type") == "entity"
    ]
