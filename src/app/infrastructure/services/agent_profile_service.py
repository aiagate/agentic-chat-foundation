"""Filesystem-backed agent profile bundle loader."""

from __future__ import annotations

from dataclasses import dataclass

import yaml
from pydantic import ValidationError

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.character_definition import CharacterDefinition
from app.contracts.messages.relationship import CharacterRelationshipDefinition
from app.contracts.ports.agent_profile_service import (
    AgentProfileServiceError,
    IAgentProfileService,
)
from app.contracts.ports.memory_store import IMemoryStore
from app.infrastructure.memory.agent_profile_markdown import (
    AgentProfileMarkdownDocument,
    AgentProfileMarkdownError,
    parse_agent_profile_markdown,
)
from app.infrastructure.memory.store import MemoryStoreError


@dataclass(slots=True)
class FilesystemAgentProfileService(IAgentProfileService):
    """Load the built-in agent profile bundle from the filesystem."""

    store: IMemoryStore
    character_id: str

    def ensure_agent_profile_bundle(self) -> None:
        """Validate that the canonical bundle files exist and parse cleanly."""

        self.load_agent_profile_bundle()

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        """Return the parsed agent profile bundle."""

        agents_document = self._read_part("AGENTS")
        soul_document = self._read_part("SOUL")
        personal_document = self._read_part("PERSONAL")
        memory_document = self._read_part("MEMORY")
        character = _load_character_definition(character_id=self.character_id)
        relationship = self._read_relationship_definition()
        persona_context = "\n\n".join(
            part
            for part in (
                agents_document.body.strip(),
                soul_document.body.strip(),
                personal_document.body.strip(),
                memory_document.body.strip(),
            )
            if part
        )
        return AgentProfileBundle(
            character=character,
            persona_context=persona_context,
            relationship=relationship,
        )

    def _read_relationship_definition(self) -> CharacterRelationshipDefinition:
        path = self.store.agent_relationship_definition_path(self.character_id)
        try:
            payload = yaml.safe_load(
                self.store.read_agent_relationship_definition(self.character_id)
            )
            return CharacterRelationshipDefinition.model_validate(payload)
        except (MemoryStoreError, yaml.YAMLError, ValidationError) as exc:
            raise AgentProfileServiceError(f"{path}: {exc}") from exc

    def _read_part(self, part: str) -> AgentProfileMarkdownDocument:
        path = self.store.agent_profile_part_path(
            part,
            character_id=self.character_id,
        )
        if path.exists():
            try:
                document = parse_agent_profile_markdown(
                    self.store.read_agent_profile_part(
                        part,
                        character_id=self.character_id,
                    ),
                    location=str(path),
                )
                if part != "PERSONAL" and document.metadata:
                    raise AgentProfileServiceError(
                        f"agent profile bundle part must not have metadata: {path}"
                    )
                return document
            except (MemoryStoreError, AgentProfileMarkdownError) as exc:
                raise AgentProfileServiceError(str(exc)) from exc

        raise AgentProfileServiceError(
            f"agent profile bundle missing required file: {path}"
        )


def _load_character_definition(
    *,
    character_id: str,
) -> CharacterDefinition:
    return CharacterDefinition(character_id=character_id)
