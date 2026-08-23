"""Semantic consolidation for Markdown long-term memories."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from flow_res import is_err

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.memory_consolidation import (
    MemoryChangeSet,
    MemoryConsolidationResult,
)
from app.contracts.messages.memory_semantic_extraction import (
    LongTermMemoryChatLog,
    MemoryEntityPatch,
    MemoryProfilePatch,
    MemorySectionSummary,
    MemorySemanticExtractionRequest,
    MemorySemanticExtractionResult,
    MemoryTimelineSectionPatch,
)
from app.contracts.messages.relationship import RelationshipSignalCandidate
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.memory_index_projection import IMemoryIndexProjection
from app.contracts.ports.memory_semantic_extraction import (
    IMemorySemanticExtractionService,
)
from app.contracts.ports.memory_store import IMemoryStore
from app.domain.queries.raw_chat_log_query import LongTermMemorySourceItem
from app.domain.value_objects.message_content import render_message_content_text
from app.infrastructure.memory.markdown import (
    MemoryMarkdownDocument,
    MemoryMarkdownError,
    front_matter_string,
    front_matter_string_list,
    front_matter_string_or_none,
)


@dataclass(frozen=True, slots=True)
class SectionConsolidationResult:
    """Result metadata for one section Timeline consolidation run."""

    section_path: Path
    section_id: str
    processed_raw_ids: list[str]
    compressed_raw_ids: list[str]
    entity_ids: list[str]


@dataclass(frozen=True, slots=True)
class _AppliedMemoryBatch:
    sections: list[SectionConsolidationResult]
    entity_paths: list[Path]
    profile_path: Path | None
    evaluated_chat_ids: list[str]
    deferred_chat_ids: list[str]
    relationship_signals: list[RelationshipSignalCandidate]


class _MissingAgentProfileService(IAgentProfileService):
    def ensure_agent_profile_bundle(self) -> None:
        raise RuntimeError("agent_profile_service is required")

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        raise RuntimeError("agent_profile_service is required")


def _missing_agent_profile_service() -> IAgentProfileService:
    return _MissingAgentProfileService()


@dataclass(frozen=True, slots=True)
class MemoryConsolidationService:
    """Write one conversation batch to the three long-term memory views.

    Semantic extraction produces profile updates, episodic timeline sections,
    and entity/relationship patches in one business operation.  This service
    owns the Markdown projection details; scheduling, source selection, and
    completion marking stay in the organizing use case.
    """

    store: IMemoryStore
    semantic_extraction_service: IMemorySemanticExtractionService | None = None
    memory_index_projection: IMemoryIndexProjection | None = None
    agent_profile_service: IAgentProfileService | None = None

    async def consolidate_chat_logs(
        self,
        *,
        user_id: str,
        day: date,
        raw_logs: list[LongTermMemorySourceItem],
        reference_time: datetime,
    ) -> MemoryConsolidationResult:
        """Consolidate one user/day raw chat log batch into Markdown memory."""

        if self.semantic_extraction_service is None:
            raise RuntimeError("semantic_extraction_service is required")

        applied = await _consolidate_chat_logs_into_sections(
            self.store,
            raw_logs,
            user_id=user_id,
            day=day,
            reference_time=_as_utc(reference_time),
            semantic_extraction_service=self.semantic_extraction_service,
            agent_profile_service=self.agent_profile_service
            or _missing_agent_profile_service(),
        )
        entity_paths = list(dict.fromkeys(applied.entity_paths))
        upsert_paths = [
            *(result.section_path for result in applied.sections),
            *entity_paths,
            *([applied.profile_path] if applied.profile_path is not None else []),
        ]
        if upsert_paths and self.memory_index_projection is not None:
            refresh_result = await self.memory_index_projection.apply_changes(
                user_id=user_id,
                upsert_paths=upsert_paths,
                delete_paths=[],
            )
            if is_err(refresh_result):
                raise RuntimeError(str(refresh_result.error))
        return MemoryConsolidationResult(
            evaluated_chat_ids=tuple(applied.evaluated_chat_ids),
            deferred_chat_ids=tuple(applied.deferred_chat_ids),
            profile_updated=applied.profile_path is not None,
            episode_upserted_count=len(applied.sections),
            entity_upserted_count=len(entity_paths),
            relationship_signals=tuple(applied.relationship_signals),
        )


async def _consolidate_chat_logs_into_sections(
    store: IMemoryStore,
    raw_logs: list[LongTermMemorySourceItem],
    *,
    user_id: str,
    day: date,
    reference_time: datetime,
    semantic_extraction_service: IMemorySemanticExtractionService,
    agent_profile_service: IAgentProfileService,
) -> _AppliedMemoryBatch:
    agent_profile_service.load_agent_profile_bundle()
    request = _build_extraction_request(
        store,
        raw_logs,
        user_id=user_id,
        day=day,
        reference_time=reference_time,
    )
    extraction_result = await semantic_extraction_service.extract_memory_updates(
        request
    )
    if is_err(extraction_result):
        raise RuntimeError(str(extraction_result.error))

    result = extraction_result.value
    raw_log_ids = _unique_strings(raw_log.id for raw_log in request.raw_logs)
    _validate_relationship_signals(result.relationship_signals, raw_log_ids)
    change_set = _build_memory_change_set(
        result,
        user_id=user_id,
        day=day,
        raw_log_ids=raw_log_ids,
    )
    results: list[SectionConsolidationResult] = []
    entity_paths: list[Path] = []
    for entity_patch in change_set.entities:
        entity_paths.append(
            _write_entity_patch(
                store,
                entity_patch=entity_patch,
                source_chat_ids=entity_patch.source_chat_ids,
                reference_time=reference_time,
            )
        )

    profile_path: Path | None = None
    if change_set.profile is not None:
        profile_path = _write_profile_patch(
            store,
            user_id=user_id,
            profile_patch=change_set.profile,
            reference_time=reference_time,
        )

    if not change_set.sections:
        return _AppliedMemoryBatch(
            sections=results,
            entity_paths=entity_paths,
            profile_path=profile_path,
            evaluated_chat_ids=list(change_set.evaluated_chat_ids),
            deferred_chat_ids=list(change_set.deferred_chat_ids),
            relationship_signals=list(result.relationship_signals),
        )

    existing_timeline_paths = set(store.iter_timeline_paths(user_id))
    observed_at = _latest_raw_chat_log_observed_at(raw_logs)
    updated_at = reference_time.isoformat()
    for section_patch in change_set.sections:
        section_result = _write_section_timeline(
            store,
            section_patch=section_patch,
            reference_time=reference_time,
            existing_timeline_paths=existing_timeline_paths,
        )
        entity_paths.extend(
            _update_entity_references(
                store,
                user_id=user_id,
                entity_ids=section_result.entity_ids,
                timeline_id=section_patch.id,
                observed_at=observed_at,
                updated_at=updated_at,
            )
        )
        results.append(section_result)
    return _AppliedMemoryBatch(
        sections=results,
        entity_paths=entity_paths,
        profile_path=profile_path,
        evaluated_chat_ids=list(change_set.evaluated_chat_ids),
        deferred_chat_ids=list(change_set.deferred_chat_ids),
        relationship_signals=list(result.relationship_signals),
    )


def _validate_relationship_signals(
    signals: list[RelationshipSignalCandidate],
    raw_log_ids: list[str],
) -> None:
    available = set(raw_log_ids)
    for signal in signals:
        if not signal.source_chat_ids:
            raise ValueError("relationship signal must cite at least one raw chat")
        if not set(signal.source_chat_ids) <= available:
            raise ValueError("relationship signal cites an unknown raw chat")


def _build_memory_change_set(
    result: MemorySemanticExtractionResult,
    *,
    user_id: str,
    day: date,
    raw_log_ids: list[str],
) -> MemoryChangeSet:
    """Validate and normalize extraction output without touching storage."""

    _validate_extraction_result(
        result, user_id=user_id, day=day, raw_log_ids=raw_log_ids
    )
    entity_patches: list[MemoryEntityPatch] = []
    entity_id_map: dict[str, str] = {}
    for patch in result.entity_patches:
        if patch.update_mode == "defer" or patch.entity_type == "relationship":
            continue
        scoped_patch = _server_scoped_entity_patch(patch, user_id=user_id)
        entity_id_map[patch.id] = scoped_patch.id
        entity_patches.append(scoped_patch)

    section_patches = [
        _server_scoped_section_patch(patch, user_id=user_id, day=day).model_copy(
            update={
                "entity_ids": [
                    entity_id_map.get(entity_id, entity_id)
                    for entity_id in patch.entity_ids
                ]
            }
        )
        for patch in result.sections
    ]
    _validate_section_source_chat_ids(
        section_patches,
        available_source_chat_ids=raw_log_ids,
    )
    profile = result.profile_patch
    if profile is not None and profile.update_mode == "defer":
        profile = None
    evaluated, deferred = _source_dispositions(result, raw_log_ids=raw_log_ids)
    return MemoryChangeSet(
        sections=tuple(section_patches),
        entities=tuple(entity_patches),
        profile=profile,
        evaluated_chat_ids=tuple(evaluated),
        deferred_chat_ids=tuple(deferred),
    )


def _build_extraction_request(
    store: IMemoryStore,
    raw_logs: list[LongTermMemorySourceItem],
    *,
    user_id: str,
    day: date,
    reference_time: datetime,
) -> MemorySemanticExtractionRequest:
    filtered_raw_logs = [
        LongTermMemoryChatLog(
            id=raw_log.id,
            user_id=raw_log.user_id,
            character_id=raw_log.character_id,
            role=raw_log.role,
            chat_type=raw_log.chat_type,
            content=_raw_chat_log_text(raw_log),
            occurred_at=_raw_chat_log_observed_at(raw_log) or reference_time,
        )
        for raw_log in raw_logs
        if raw_log.created_at is not None and _as_jst(raw_log.created_at).date() == day
    ]
    return MemorySemanticExtractionRequest(
        user_id=user_id,
        day=day.isoformat(),
        raw_logs=filtered_raw_logs,
        existing_profile_summary=_existing_profile_summary(store, user_id=user_id),
        existing_entity_labels=_existing_entity_labels(store, user_id=user_id),
        existing_timeline_summaries=_recent_timeline_summaries(
            store,
            user_id=user_id,
            before_day=day,
            limit_days=3,
        ),
    )


def _existing_profile_summary(store: IMemoryStore, *, user_id: str) -> str | None:
    path = store.user_profile_path(user_id)
    if not path.exists():
        return None
    document = store.read_document(
        path,
        expected_memory_type="profile",
        expected_user_id=user_id,
    )
    front_matter = document.front_matter
    values = [
        f"summary={front_matter_string(front_matter.get('summary'))}",
        "traits=" + ", ".join(front_matter_string_list(front_matter.get("traits"))),
        "preferences="
        + ", ".join(front_matter_string_list(front_matter.get("preferences"))),
    ]
    return "; ".join(values)


def _validate_extraction_result(
    result: MemorySemanticExtractionResult,
    *,
    user_id: str,
    day: date,
    raw_log_ids: list[str],
) -> None:
    available = set(raw_log_ids)
    referenced: set[str] = set()
    for section in result.sections:
        if section.user_id != user_id or section.day != day.isoformat():
            raise ValueError("Memory section scope does not match the requested batch")
        _validate_confidence(section.confidence)
        referenced.update(section.source_chat_ids)
    for entity in result.entity_patches:
        if entity.user_id != user_id:
            raise ValueError("Memory entity scope does not match the requested user")
        _validate_confidence(entity.confidence)
        if entity.update_mode != "defer" and not entity.source_chat_ids:
            raise ValueError("Memory entity patch requires source_chat_ids")
        referenced.update(entity.source_chat_ids)
    if result.profile_patch is not None:
        profile = result.profile_patch
        if profile.user_id != user_id:
            raise ValueError("Memory profile scope does not match the requested user")
        _validate_confidence(profile.confidence)
        if profile.update_mode != "defer" and not profile.source_chat_ids:
            raise ValueError("Memory profile patch requires source_chat_ids")
        referenced.update(profile.source_chat_ids)
    for signal in result.relationship_signals:
        _validate_confidence(signal.confidence)
        if not signal.source_chat_ids:
            raise ValueError("Relationship signal requires source_chat_ids")
        referenced.update(signal.source_chat_ids)
    if not referenced.issubset(available):
        unknown = sorted(referenced - available)
        raise ValueError(f"Memory patches reference unknown source chat ids: {unknown}")
    if raw_log_ids and not result.source_evaluations:
        raise ValueError("Source evaluations must cover the entire input batch")
    if result.source_evaluations:
        evaluation_ids = [item.chat_id for item in result.source_evaluations]
        if len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("Each source chat must have one evaluation")
        if set(evaluation_ids) != available:
            raise ValueError("Source evaluations must cover the entire input batch")
        used_ids = {
            item.chat_id
            for item in result.source_evaluations
            if item.disposition == "used"
        }
        if used_ids != referenced:
            raise ValueError("Used source evaluations must match patch evidence")


def _validate_confidence(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError("Memory confidence must be between 0 and 1")


def _source_dispositions(
    result: MemorySemanticExtractionResult,
    *,
    raw_log_ids: list[str],
) -> tuple[list[str], list[str]]:
    evaluated = [
        item.chat_id
        for item in result.source_evaluations
        if item.disposition in {"used", "not_memorable"}
    ]
    deferred = [
        item.chat_id
        for item in result.source_evaluations
        if item.disposition == "deferred"
    ]
    return evaluated, deferred


def _server_scoped_section_patch(
    patch: MemoryTimelineSectionPatch,
    *,
    user_id: str,
    day: date,
) -> MemoryTimelineSectionPatch:
    source_key = "\x1f".join(sorted(set(patch.source_chat_ids)))
    digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:16]
    return patch.model_copy(
        update={
            "id": f"episode-{day.isoformat()}-{digest}",
            "user_id": user_id,
            "day": day.isoformat(),
            "section_slug": digest,
        }
    )


def _server_scoped_entity_patch(
    patch: MemoryEntityPatch,
    *,
    user_id: str,
) -> MemoryEntityPatch:
    identity = f"{patch.entity_type.strip().lower()}\x1f{patch.label.strip().lower()}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return patch.model_copy(update={"id": f"entity-{digest}", "user_id": user_id})


def _write_profile_patch(
    store: IMemoryStore,
    *,
    user_id: str,
    profile_patch: MemoryProfilePatch,
    reference_time: datetime,
) -> Path:
    path = store.user_profile_path(user_id)
    existing = (
        store.read_document(
            path,
            expected_memory_type="profile",
            expected_user_id=user_id,
        )
        if path.exists()
        else None
    )
    current = dict(existing.front_matter) if existing is not None else {}
    current_traits = front_matter_string_list(current.get("traits", []))
    current_preferences = front_matter_string_list(current.get("preferences", []))
    if profile_patch.update_mode == "replace":
        traits = _unique_strings(profile_patch.traits)
        preferences = _unique_strings(profile_patch.preferences)
    else:
        traits = _unique_strings([*current_traits, *profile_patch.traits])
        preferences = _unique_strings(
            [*current_preferences, *profile_patch.preferences]
        )
    summary = profile_patch.summary
    if summary is None:
        summary = front_matter_string(current.get("summary"))
    display_name = profile_patch.display_name
    if display_name is None:
        display_name = front_matter_string_or_none(current.get("display_name"))
    observed_at = (profile_patch.observed_at or reference_time).isoformat()
    source_ids = _unique_strings(
        [
            *front_matter_string_list(current.get("source_chat_ids", [])),
            *profile_patch.source_chat_ids,
        ]
    )
    front_matter: dict[str, object] = {
        "schema_version": 1,
        "memory_type": "profile",
        "id": f"profile:{user_id}",
        "memory_id": f"profile:{user_id}",
        "user_id": user_id,
        "profile_scope": "user",
        "display_name": display_name,
        "summary": summary,
        "traits": traits,
        "preferences": preferences,
        "source_chat_ids": source_ids,
        "observed_at": observed_at,
        "created_at": front_matter_string(
            current.get("created_at"), default=reference_time.isoformat()
        ),
        "updated_at": reference_time.isoformat(),
        "tags": ["profile"],
        "importance": 0.8,
        "confidence": profile_patch.confidence,
        "pinned": False,
        "metadata": {"update_mode": profile_patch.update_mode},
    }
    body_lines = [
        f"# {display_name or user_id}",
        "",
        "## Summary",
        "",
        summary or "",
        "",
        "## Traits",
        "",
        *(f"- {value}" for value in traits),
        "",
        "## Preferences",
        "",
        *(f"- {value}" for value in preferences),
    ]
    store.write_document(path, front_matter=front_matter, body="\n".join(body_lines))
    return path


def _write_entity_patch(
    store: IMemoryStore,
    *,
    entity_patch: MemoryEntityPatch,
    source_chat_ids: list[str],
    reference_time: datetime,
) -> Path:
    entity_path = store.entity_path(entity_patch.user_id, entity_patch.id)
    existing_document = _read_existing_entity(
        store,
        entity_path,
        user_id=entity_patch.user_id,
    )
    existing_front_matter = (
        dict(existing_document.front_matter) if existing_document is not None else {}
    )
    existing_properties = _property_dict(existing_front_matter.get("properties") or {})
    patch_properties = _property_dict(entity_patch.properties)
    property_history = _mapping_list(existing_front_matter.get("property_history"))
    if entity_patch.update_mode == "replace":
        properties = patch_properties
    else:
        properties = {**existing_properties, **patch_properties}
    if entity_patch.update_mode == "transition":
        observed_at = (entity_patch.observed_at or reference_time).isoformat()
        for key, value in patch_properties.items():
            previous = existing_properties.get(key)
            if previous is not None and previous != value:
                property_history.append(
                    {
                        "key": key,
                        "value": previous,
                        "valid_to": observed_at,
                        "source_chat_ids": front_matter_string_list(
                            existing_front_matter.get("source_chat_ids", [])
                        ),
                    }
                )
    entity_type = entity_patch.entity_type
    label = entity_patch.label
    tags = front_matter_string_list(existing_front_matter.get("tags", []))
    importance = max(
        _float_value(existing_front_matter.get("importance"), default=0.0),
        0.6,
    )

    aliases = _unique_strings(
        [
            *front_matter_string_list(existing_front_matter.get("aliases", [])),
            *entity_patch.aliases,
        ]
    )
    previous_source_chat_ids = front_matter_string_list(
        existing_front_matter.get("source_chat_ids", [])
    )
    front_matter: dict[str, object] = {
        "schema_version": 1,
        "memory_type": "entity",
        "id": entity_patch.id,
        "user_id": entity_patch.user_id,
        "label": label,
        "entity_type": entity_type,
        "status": entity_patch.status or "active",
        "aliases": aliases,
        "properties": properties,
        "property_history": property_history,
        "missing_attributes": entity_patch.missing_attributes,
        "referenced_in": front_matter_string_list(
            existing_front_matter.get("referenced_in", [])
        ),
        "source_chat_ids": _unique_strings(
            [*previous_source_chat_ids, *source_chat_ids]
        ),
        "created_at": front_matter_string(
            existing_front_matter.get("created_at"),
            default=reference_time.isoformat(),
        ),
        "updated_at": reference_time.isoformat(),
        "tags": tags,
        "importance": importance,
        "confidence": max(
            _float_value(existing_front_matter.get("confidence"), default=0.0),
            entity_patch.confidence,
        ),
        "pinned": bool(existing_front_matter.get("pinned")),
        "metadata": existing_front_matter.get("metadata", {}),
        "observed_at": (entity_patch.observed_at or reference_time).isoformat(),
        "update_mode": entity_patch.update_mode,
    }
    store.write_document(
        entity_path,
        front_matter=front_matter,
        body=_build_entity_body(
            label=label,
            entity_type=entity_type,
            status=front_matter_string(front_matter.get("status"), default="active"),
            properties=properties,
        ),
    )
    return entity_path


def _write_section_timeline(
    store: IMemoryStore,
    *,
    section_patch: MemoryTimelineSectionPatch,
    reference_time: datetime,
    existing_timeline_paths: set[Path] | None = None,
) -> SectionConsolidationResult:
    day = datetime.fromisoformat(section_patch.day).date()
    summary_of = _unique_strings(section_patch.source_chat_ids)
    section_path = store.section_timeline_path(
        user_id=section_patch.user_id,
        day=day,
        section_slug=section_patch.section_slug,
    )
    existing_section_match = _find_existing_section_by_source_ids(
        store,
        user_id=section_patch.user_id,
        day=day,
        source_chat_ids=summary_of,
        candidate_paths=existing_timeline_paths,
    )
    if existing_section_match is None:
        existing_section = _read_existing_section(
            store,
            section_path,
            user_id=section_patch.user_id,
        )
        resolved_section_id = section_patch.id
        resolved_section_slug = section_patch.section_slug
        resolved_title = section_patch.title
    else:
        section_path, existing_section = existing_section_match
        existing_front_matter = existing_section.front_matter
        resolved_section_id = front_matter_string(
            existing_front_matter.get("id"),
            default=section_patch.id,
        )
        resolved_section_slug = front_matter_string(
            existing_front_matter.get("section_slug"),
            default=section_patch.section_slug,
        )
        resolved_title = front_matter_string(
            existing_front_matter.get("section_title"),
            default=section_patch.title,
        )
    body = _build_semantic_section_body(
        day=day,
        title=resolved_title,
        summary=section_patch.summary,
    )
    entity_ids = _unique_strings(section_patch.entity_ids)
    front_matter = _section_front_matter(
        existing_section,
        user_id=section_patch.user_id,
        section_id=resolved_section_id,
        day=day,
        section_slug=resolved_section_slug,
        title=resolved_title,
        summary_of=summary_of,
        entity_ids=entity_ids,
        summary=section_patch.summary,
        content=body,
        now=reference_time,
    )
    front_matter["source_chat_ids"] = summary_of
    front_matter["extraction_confidence"] = section_patch.confidence
    store.write_document(
        section_path,
        front_matter=front_matter,
        body=body,
    )
    return SectionConsolidationResult(
        section_path=section_path,
        section_id=section_patch.id,
        processed_raw_ids=summary_of,
        compressed_raw_ids=[],
        entity_ids=entity_ids,
    )


def _read_existing_entity(
    store: IMemoryStore,
    entity_path: Path,
    *,
    user_id: str,
) -> MemoryMarkdownDocument | None:
    if not entity_path.exists():
        return None
    return store.read_document(
        entity_path,
        expected_memory_type="entity",
        expected_user_id=user_id,
    )


def _existing_entity_labels(
    store: IMemoryStore,
    *,
    user_id: str,
) -> list[str]:
    labels: list[str] = []
    for path in store.iter_entity_paths(user_id):
        try:
            document = store.read_document(
                path,
                expected_memory_type="entity",
                expected_user_id=user_id,
            )
        except MemoryMarkdownError:
            continue
        front_matter = document.front_matter
        label = front_matter_string(front_matter.get("label"))
        if label:
            labels.append(
                f"id={front_matter_string(front_matter.get('id'))}; "
                f"label={label}; "
                f"type={front_matter_string(front_matter.get('entity_type'))}; "
                f"properties={front_matter.get('properties', {})}"
            )
    return labels


def _build_entity_body(
    *,
    label: str,
    entity_type: str,
    status: str,
    properties: Mapping[str, object],
) -> str:
    lines = [
        f"# {label}",
        "",
        f"- type: {entity_type}",
        f"- status: {status}",
    ]
    if properties:
        lines.extend(["", "## Known Facts", ""])
        for key, value in sorted(properties.items()):
            lines.append(f"- {key}: {_format_property(value)}")
    return "\n".join(lines)


def _validate_section_source_chat_ids(
    section_patches: list[MemoryTimelineSectionPatch],
    *,
    available_source_chat_ids: list[str],
) -> None:
    available_ids = set(available_source_chat_ids)
    assigned_ids: set[str] = set()
    for section_patch in section_patches:
        source_ids = section_patch.source_chat_ids
        if len(source_ids) != len(set(source_ids)):
            raise ValueError(
                f"Section {section_patch.id!r} contains duplicate source_chat_ids"
            )
        unknown_ids = set(source_ids) - available_ids
        if unknown_ids:
            raise ValueError(
                f"Section {section_patch.id!r} references unknown source_chat_ids: "
                f"{sorted(unknown_ids)!r}"
            )
        overlapping_ids = assigned_ids.intersection(source_ids)
        if overlapping_ids:
            raise ValueError(
                "source_chat_ids must belong to exactly one section; "
                f"overlapping ids: {sorted(overlapping_ids)!r}"
            )
        assigned_ids.update(source_ids)


def _build_semantic_section_body(
    *,
    day: date,
    title: str,
    summary: MemorySectionSummary,
) -> str:
    lines = ["# " + title, "", f"## {day.isoformat()} の要約", ""]
    lines.extend(
        [
            f"- 何について話した: {summary.topic}",
            f"- 自分がどう感じたか: {summary.self_feeling}",
            f"- 相手がどう感じていそうか: {summary.other_feeling}",
            f"- 結果として残ったこと: {summary.outcome}",
        ]
    )
    return "\n".join(lines)


def _section_manifest_summary(summary: MemorySectionSummary) -> str:
    parts = [
        summary.topic.strip(),
        summary.outcome.strip(),
    ]
    return " | ".join(part for part in parts if part)


def _recent_timeline_summaries(
    store: IMemoryStore,
    *,
    user_id: str,
    before_day: date,
    limit_days: int,
) -> list[str]:
    grouped: dict[date, list[str]] = defaultdict(list)
    for path in store.iter_timeline_paths(user_id):
        try:
            document = store.read_document(
                path,
                expected_memory_type="timeline",
                expected_user_id=user_id,
            )
        except MemoryMarkdownError:
            continue
        front_matter = document.front_matter
        if front_matter.get("timeline_type") != "section_summary":
            continue
        occurred_at = _front_matter_day(front_matter.get("occurred_at"))
        if occurred_at is None or occurred_at >= before_day:
            continue
        grouped[occurred_at].append(_timeline_document_summary(document))

    recent_days = sorted(grouped)[-limit_days:]
    return [f"{day.isoformat()}: " + " / ".join(grouped[day]) for day in recent_days]


def _timeline_document_summary(document: MemoryMarkdownDocument) -> str:
    front_matter = document.front_matter
    title = front_matter_string(
        front_matter.get("section_title") or front_matter.get("kind"),
        default="要約",
    )
    body_lines = [
        line.strip()
        for line in document.body.splitlines()
        if line.strip().startswith("- ")
    ]
    body_excerpt = " ".join(body_lines[:4]) if body_lines else document.body.strip()
    normalized_excerpt = " ".join(body_excerpt.split())
    if normalized_excerpt:
        return f"{title}: {normalized_excerpt}"
    return title


def _front_matter_day(value: object) -> date | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(
            front_matter_string(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None
    return parsed.date()


def _read_existing_section(
    store: IMemoryStore,
    section_path: Path,
    *,
    user_id: str,
) -> MemoryMarkdownDocument | None:
    if not section_path.exists():
        return None
    return store.read_document(
        section_path,
        expected_memory_type="timeline",
        expected_user_id=user_id,
    )


def _find_existing_section_by_source_ids(
    store: IMemoryStore,
    *,
    user_id: str,
    day: date,
    source_chat_ids: list[str],
    candidate_paths: set[Path] | None = None,
) -> tuple[Path, MemoryMarkdownDocument] | None:
    if not source_chat_ids:
        return None
    expected_source_ids = set(source_chat_ids)
    paths = (
        sorted(candidate_paths)
        if candidate_paths is not None
        else store.iter_timeline_paths(user_id)
    )
    for path in paths:
        try:
            document = store.read_document(
                path,
                expected_memory_type="timeline",
                expected_user_id=user_id,
            )
        except MemoryMarkdownError:
            continue
        front_matter = document.front_matter
        if front_matter.get("timeline_type") != "section_summary":
            continue
        if _front_matter_day(front_matter.get("occurred_at")) != day:
            continue
        existing_source_ids = set(_section_source_chat_ids(front_matter))
        if existing_source_ids == expected_source_ids:
            return path, document
    return None


def _section_source_chat_ids(front_matter: Mapping[str, object]) -> list[str]:
    source_chat_ids = front_matter_string_list(front_matter.get("source_chat_ids"))
    if source_chat_ids:
        return source_chat_ids
    return front_matter_string_list(front_matter.get("summary_of"))


def _section_front_matter(
    existing_section: MemoryMarkdownDocument | None,
    *,
    user_id: str,
    section_id: str,
    day: date,
    section_slug: str,
    title: str,
    summary_of: list[str],
    entity_ids: list[str],
    summary: MemorySectionSummary,
    content: str,
    now: datetime,
) -> dict[str, object]:
    existing_front_matter = (
        dict(existing_section.front_matter) if existing_section is not None else {}
    )
    created_at = front_matter_string(
        existing_front_matter.get("created_at"),
        default=now.isoformat(),
    )
    memory_id = f"timeline:{section_id}"
    manifest_summary = front_matter_string_or_none(
        existing_front_matter.get("manifest_summary")
    ) or _section_manifest_summary(summary)
    return {
        "schema_version": 1,
        "memory_type": "timeline",
        "id": section_id,
        "memory_id": memory_id,
        "user_id": user_id,
        "timeline_type": "section_summary",
        "kind": "summary",
        "content": content,
        "manifest_title": title,
        "manifest_summary": manifest_summary,
        "occurred_at": datetime.combine(day, time.min, tzinfo=UTC).isoformat(),
        "source": "consolidation",
        "entity_ids": entity_ids,
        "summary_of": summary_of,
        "section_slug": section_slug,
        "section_title": title,
        "consolidation_state": "complete",
        "retention_state": front_matter_string(
            existing_front_matter.get("retention_state"),
            default="active",
        ),
        "last_accessed_at": existing_front_matter.get("last_accessed_at"),
        "access_count": existing_front_matter.get("access_count", 0),
        "decay_score": 1.0,
        "created_at": created_at,
        "updated_at": now.isoformat(),
        "tags": _unique_strings(
            [
                *front_matter_string_list(existing_front_matter.get("tags", [])),
                "timeline",
                "summary",
            ]
        ),
        "importance": max(
            _float_value(existing_front_matter.get("importance"), default=0.0),
            0.6,
        ),
        "confidence": max(
            _float_value(existing_front_matter.get("confidence"), default=0.0),
            1.0,
        ),
        "pinned": existing_front_matter.get("pinned") is True,
        "metadata": existing_front_matter.get("metadata", {}),
    }


def _update_entity_references(
    store: IMemoryStore,
    *,
    user_id: str,
    entity_ids: list[str],
    timeline_id: str,
    observed_at: str | None,
    updated_at: str,
) -> list[Path]:
    updated_paths: list[Path] = []
    for entity_id in entity_ids:
        entity_path = store.entity_path(user_id, entity_id)
        if not entity_path.exists():
            continue
        document = store.read_document(
            entity_path,
            expected_memory_type="entity",
            expected_user_id=user_id,
        )
        front_matter = dict(document.front_matter)
        referenced_in = _unique_strings(
            [
                *front_matter_string_list(front_matter.get("referenced_in", [])),
                timeline_id,
            ]
        )
        front_matter["referenced_in"] = referenced_in
        if observed_at is not None:
            front_matter["last_observed_at"] = observed_at
        front_matter["updated_at"] = updated_at
        store.write_document(
            entity_path,
            front_matter=front_matter,
            body=document.body,
        )
        updated_paths.append(entity_path)
    return updated_paths


def _latest_raw_chat_log_observed_at(
    raw_logs: list[LongTermMemorySourceItem],
) -> str | None:
    occurred_values = [_raw_chat_log_observed_at(raw_log) for raw_log in raw_logs]
    observed_values = [value for value in occurred_values if value is not None]
    if not observed_values:
        return None
    return max(observed_values).isoformat()


def _raw_chat_log_observed_at(
    raw_log: LongTermMemorySourceItem,
) -> datetime | None:
    if raw_log.created_at is None:
        return None
    return _as_utc(raw_log.created_at)


def _raw_chat_log_text(raw_log: LongTermMemorySourceItem) -> str:
    payload = raw_log.message_content.get("payload")
    if isinstance(payload, dict):
        text = render_message_content_text(payload)
        if isinstance(text, str):
            return text
    return front_matter_string(raw_log.message_content)


def _unique_strings(values: Iterable[str]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values


def _property_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    properties: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, str | int | float | bool) or item is None:
            properties[str(key)] = item
        elif isinstance(item, list):
            properties[str(key)] = [
                list_item
                for list_item in item
                if isinstance(list_item, str | int | float | bool)
            ]
        else:
            properties[str(key)] = front_matter_string(item)
    return properties


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _format_property(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _float_value(value: object, *, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _as_utc(value: datetime) -> datetime:
    return (
        value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    )


def _as_jst(value: datetime) -> datetime:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(ZoneInfo("Asia/Tokyo"))
