"""Filesystem-backed memory service for the app layer."""

from __future__ import annotations

from flow_res import Err, Ok, Result

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.memory_context import MemoryContextPack, MemoryReadResult
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.memory_service import IMemoryService, MemoryServiceError
from app.infrastructure.memory.context_formatter import (
    manifest_item_from_document,
    memory_read_result_from_document,
    render_manifest_context,
)
from app.infrastructure.memory.context_loader import (
    read_entities,
    read_index_documents,
    read_profile,
    read_timelines,
)
from app.infrastructure.memory.markdown import MemoryMarkdownError
from app.infrastructure.memory.store import (
    FilesystemMemoryStore,
    MemoryStoreError,
    default_memory_root,
)


class FilesystemMemoryService(IMemoryService):
    """Adapter that retrieves memory from the local filesystem."""

    def __init__(
        self,
        store: FilesystemMemoryStore | None = None,
        index: object | None = None,
        agent_profile_service: IAgentProfileService | None = None,
        *,
        character_id: str,
    ) -> None:
        self._store = store or FilesystemMemoryStore(default_memory_root())
        del index
        self._agent_profile_service = agent_profile_service
        self._character_id = character_id

    async def build_context(
        self,
        user_id: str,
    ) -> Result[MemoryContextPack, MemoryServiceError]:
        """Return a prompt-ready compact manifest for the user scope."""

        try:
            profile_bundle = self._load_profile_bundle()
            relationship_entity_id = self._relationship_entity_id(profile_bundle)
            index_documents = read_index_documents(
                self._store,
                user_id,
                character_id=self._character_id,
                relationship_entity_id=relationship_entity_id,
            )
            manifest_items = [
                manifest_item_from_document(document) for document in index_documents
            ]
            return Ok(
                MemoryContextPack(
                    user_id=user_id,
                    assembled_context=render_manifest_context(manifest_items),
                    manifest_items=manifest_items,
                    profile=(
                        profile_bundle.profile
                        if profile_bundle is not None
                        else read_profile(self._store, user_id)
                    ),
                    timelines=read_timelines(self._store, user_id),
                    entities=read_entities(
                        self._store,
                        user_id,
                        relationship_entity_id=relationship_entity_id,
                    ),
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
            relationship_entity_id = self._relationship_entity_id(
                self._load_profile_bundle()
            )
            index_documents = read_index_documents(
                self._store,
                user_id,
                character_id=self._character_id,
                relationship_entity_id=relationship_entity_id,
            )
            for document in index_documents:
                manifest_item = manifest_item_from_document(document)
                if manifest_item.memory_id != memory_id:
                    continue
                return Ok(memory_read_result_from_document(document, manifest_item))
            return Err(MemoryServiceError(f"Memory not found: {memory_id}"))
        except (MemoryMarkdownError, MemoryStoreError, OSError, ValueError) as exc:
            return Err(MemoryServiceError(str(exc)))

    def _load_profile_bundle(self) -> AgentProfileBundle | None:
        if self._agent_profile_service is None:
            return None
        return self._agent_profile_service.load_agent_profile_bundle()

    def _relationship_entity_id(
        self,
        profile_bundle: AgentProfileBundle | None,
    ) -> str:
        if profile_bundle is None:
            return f"relationship:{self._character_id}"
        return profile_bundle.relationship_entity_id
