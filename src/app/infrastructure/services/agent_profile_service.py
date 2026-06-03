"""Filesystem-backed agent profile bundle loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.character_definition import (
    CharacterDefinition,
    RelationshipDefaults,
    selected_character_definition,
)
from app.contracts.messages.memory_context import MemoryProfile
from app.contracts.ports.agent_profile_service import (
    AgentProfileServiceError,
    IAgentProfileService,
)
from app.contracts.ports.memory_store import IMemoryStore
from app.infrastructure.memory.markdown import (
    MemoryMarkdownDocument,
    front_matter_string,
    front_matter_string_list,
    front_matter_string_or_none,
)


@dataclass(slots=True)
class FilesystemAgentProfileService(IAgentProfileService):
    """Load the built-in agent profile bundle from the filesystem."""

    store: IMemoryStore
    character: CharacterDefinition | None = None

    def __post_init__(self) -> None:
        self._store = self.store
        self._character = self.character or selected_character_definition()

    def ensure_agent_profile_bundle(self) -> None:
        """Validate that the canonical bundle files exist and parse cleanly."""

        self.load_agent_profile_bundle()

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        """Return the parsed agent profile bundle."""

        agents_document = self._read_part("AGENTS")
        soul_document = self._read_part("SOUL")
        personal_document = self._read_part("PERSONAL")
        memory_document = self._read_part("MEMORY")
        profile = _load_profile(
            agents_document=agents_document,
            soul_document=soul_document,
            personal_document=personal_document,
            character=self._character,
        )
        persona_context = agents_document.body.strip()
        communication_style = _body_section_list(
            agents_document.body, "Communication Style"
        )
        known_constraints = _body_section_list(
            agents_document.body, "Known Constraints"
        )
        atmosphere = _body_section_list(soul_document.body, "Atmosphere")
        behavior = _body_section_list(soul_document.body, "ふるまい")
        relationship_section = _section_key_values(
            personal_document.body, "Relationship"
        )
        fallback = _body_section_list(personal_document.body, "Fallback")
        memory_reading_rules = _body_section_list(memory_document.body, "Reading rule")
        relationship_entity_id = (
            relationship_section.get("relationship_entity_id")
            or self._character.relationship_entity_id
        )
        relationship_entity_label = (
            relationship_section.get("relationship_entity_label")
            or self._character.relationship_entity_label
        )
        relationship_entity_type = (
            relationship_section.get("relationship_entity_type")
            or self._character.relationship_entity_type
        )
        relationship_tag = (
            relationship_section.get("relationship_tag")
            or self._character.relationship_tag
        )
        relationship_defaults = RelationshipDefaults(
            trust_score=_section_float(
                relationship_section,
                "relationship_initial_trust_score",
                default=self._character.relationship_defaults.trust_score,
            ),
            warmth_score=_section_float(
                relationship_section,
                "relationship_initial_warmth_score",
                default=self._character.relationship_defaults.warmth_score,
            ),
            stage=_section_int(
                relationship_section,
                "relationship_initial_stage",
                default=self._character.relationship_defaults.stage,
            ),
        )
        missing_fields = [
            field_name
            for field_name, value in (
                ("relationship_entity_id", relationship_entity_id),
                ("relationship_entity_label", relationship_entity_label),
                ("relationship_entity_type", relationship_entity_type),
                ("relationship_tag", relationship_tag),
            )
            if not value
        ]
        if missing_fields:
            joined = ", ".join(missing_fields)
            raise AgentProfileServiceError(
                f"agent profile bundle is missing required relationship fields: {joined}"
            )
        return AgentProfileBundle(
            profile=profile,
            character=self._character,
            persona_context=persona_context,
            communication_style=tuple(communication_style),
            known_constraints=tuple(known_constraints),
            atmosphere=tuple(atmosphere),
            behavior=tuple(behavior),
            relationship_entity_id=relationship_entity_id,
            relationship_entity_label=relationship_entity_label,
            relationship_entity_type=relationship_entity_type,
            relationship_tag=relationship_tag,
            relationship_defaults=relationship_defaults,
            relationship=tuple(
                _body_section_list(personal_document.body, "Relationship")
            ),
            fallback=tuple(fallback),
            memory_reading_rules=tuple(memory_reading_rules),
        )

    def _read_part(self, part: str) -> MemoryMarkdownDocument:
        path = self._store.agent_profile_part_path(
            part,
            character_id=self._character.character_id,
        )
        if path.exists():
            return self._store.read_document(path, expected_memory_type="profile")

        legacy_path = _legacy_agent_profile_part_path(self._store.root, part)
        if legacy_path.exists():
            return self._store.read_document(
                legacy_path,
                expected_memory_type="profile",
            )

        raise AgentProfileServiceError(
            f"agent profile bundle missing required file: {path}"
        )


def _legacy_agent_profile_part_path(root: Path, part: str) -> Path:
    normalized = part.upper()
    return root / "profiles" / "agent" / f"{normalized}.md"


def _load_profile(
    *,
    agents_document: MemoryMarkdownDocument,
    soul_document: MemoryMarkdownDocument,
    personal_document: MemoryMarkdownDocument,
    character: CharacterDefinition,
) -> MemoryProfile:
    display_name = (
        front_matter_string_or_none(agents_document.front_matter.get("display_name"))
        or _body_h1_text(agents_document.body)
        or _body_h1_text(soul_document.body)
        or _body_h1_text(personal_document.body)
    )
    summary = front_matter_string(
        soul_document.front_matter.get("summary")
    ) or _body_section_text(soul_document.body, "Summary")
    traits = front_matter_string_list(soul_document.front_matter.get("traits", []))
    if not traits:
        traits = _body_section_list(soul_document.body, "Traits")
    preferences = front_matter_string_list(
        personal_document.front_matter.get("preferences", [])
    )
    if not preferences:
        preferences = _body_section_list(personal_document.body, "Preferences")
    user_id = front_matter_string_or_none(agents_document.front_matter.get("user_id"))
    if not user_id:
        user_id = character.profile_user_id
    return MemoryProfile(
        user_id=user_id,
        display_name=display_name,
        summary=summary,
        traits=traits,
        preferences=preferences,
    )


def _body_section_text(body: str, section_name: str) -> str:
    lines = _body_section_lines(body, section_name)
    return "\n".join(line.strip() for line in lines).strip()


def _body_section_list(body: str, section_name: str) -> list[str]:
    lines = _body_section_lines(body, section_name)
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            values.append(stripped[2:].strip())
    return values


def _body_section_lines(body: str, section_name: str) -> list[str]:
    if not body:
        return []
    lines = body.splitlines()
    captured: list[str] = []
    active = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            active = stripped[3:].strip().lower() == section_name.lower()
            continue
        if active:
            captured.append(line)
    return captured


def _body_h1_text(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            value = stripped[2:].strip()
            if value:
                return value
    return None


def _section_key_values(body: str, section_name: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in _body_section_lines(body, section_name):
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        kv_text = stripped[2:].strip()
        if ": " not in kv_text:
            continue
        key, value = kv_text.split(": ", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            values[key] = value
    return values


def _section_float(
    values: dict[str, str],
    key: str,
    *,
    default: float,
) -> float:
    raw = values.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _section_int(
    values: dict[str, str],
    key: str,
    *,
    default: int,
) -> int:
    raw = values.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
