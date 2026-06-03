"""Semantic sleep/consolidation for Markdown Timeline memories."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path

from flow_res import is_err

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.character_definition import RelationshipDefaults
from app.contracts.messages.memory_semantic_extraction import (
    MemoryEntityPatch,
    MemorySectionSummary,
    MemorySemanticExtractionRequest,
    MemorySleepChatLog,
    MemoryTimelinePatch,
    MemoryTimelineSectionPatch,
)
from app.contracts.messages.relationship_growth import (
    MAX_DAILY_SCORE_INCREASE,
    clamp_relationship_score_increase,
    resolve_relationship_stage,
)
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.memory_index_maintenance import IMemoryIndexMaintenance
from app.contracts.ports.memory_semantic_extraction import (
    IMemorySemanticExtractionService,
)
from app.contracts.ports.memory_store import IMemoryStore
from app.domain.queries.raw_chat_log_query import RawChatLog
from app.infrastructure.memory.markdown import (
    MemoryMarkdownDocument,
    MemoryMarkdownError,
    front_matter_string,
    front_matter_string_list,
)


@dataclass(frozen=True, slots=True)
class SectionConsolidationResult:
    """Result metadata for one section Timeline consolidation run."""

    section_path: Path
    section_id: str
    processed_raw_ids: list[str]
    compressed_raw_ids: list[str]
    entity_ids: list[str]


class _MissingAgentProfileService(IAgentProfileService):
    def ensure_agent_profile_bundle(self) -> None:
        raise RuntimeError("agent_profile_service is required")

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        raise RuntimeError("agent_profile_service is required")


def _missing_agent_profile_service() -> IAgentProfileService:
    return _MissingAgentProfileService()


@dataclass(frozen=True, slots=True)
class MemoryConsolidationService:
    """LLM-backed consolidation service for Markdown memory storage."""

    semantic_extraction_service: IMemorySemanticExtractionService | None = None
    memory_index_maintenance: IMemoryIndexMaintenance | None = None
    agent_profile_service: IAgentProfileService | None = None

    async def consolidate_chat_logs(
        self,
        store: IMemoryStore,
        *,
        user_id: str,
        day: date,
        raw_logs: list[RawChatLog],
        reference_time: datetime,
    ) -> int:
        """Consolidate one user/day raw chat log batch into Markdown memory."""

        if self.semantic_extraction_service is None:
            raise RuntimeError("semantic_extraction_service is required")

        results, wrote_entity_patches = await _consolidate_chat_logs_into_sections(
            store,
            raw_logs,
            user_id=user_id,
            day=day,
            reference_time=_as_utc(reference_time),
            semantic_extraction_service=self.semantic_extraction_service,
            agent_profile_service=self.agent_profile_service
            or _missing_agent_profile_service(),
        )
        if (
            results or wrote_entity_patches
        ) and self.memory_index_maintenance is not None:
            await self.memory_index_maintenance.rebuild_memory_index(user_id=user_id)
        return len(results)


async def _consolidate_chat_logs_into_sections(
    store: IMemoryStore,
    raw_logs: list[RawChatLog],
    *,
    user_id: str,
    day: date,
    reference_time: datetime,
    semantic_extraction_service: IMemorySemanticExtractionService,
    agent_profile_service: IAgentProfileService,
) -> tuple[list[SectionConsolidationResult], bool]:
    profile_bundle = agent_profile_service.load_agent_profile_bundle()
    request = MemorySemanticExtractionRequest(
        user_id=user_id,
        day=day.isoformat(),
        raw_logs=[
            MemorySleepChatLog(
                id=raw_log.id,
                user_id=raw_log.user_id,
                role=raw_log.role,
                chat_type=raw_log.chat_type,
                content=_raw_chat_log_text(raw_log),
                occurred_at=_raw_chat_log_observed_at(raw_log) or reference_time,
            )
            for raw_log in raw_logs
            if raw_log.created_at is not None
            and _as_utc(raw_log.created_at).date() == day
        ],
        existing_profile_summary=None,
        existing_entity_labels=_existing_entity_labels(store, user_id=user_id),
        existing_timeline_summaries=_recent_timeline_summaries(
            store,
            user_id=user_id,
            before_day=day,
            limit_days=3,
        ),
    )
    extraction_result = await semantic_extraction_service.extract_memory_updates(
        request
    )
    if is_err(extraction_result):
        raise RuntimeError(str(extraction_result.error))

    result = extraction_result.value
    section_patches = result.sections
    if not section_patches and result.timeline_patch is not None:
        section_patches = [
            _timeline_patch_to_section_patch(
                result.timeline_patch,
                fallback_slug="summary",
            )
        ]

    results: list[SectionConsolidationResult] = []
    wrote_entity_patches = False
    for entity_patch in result.entity_patches:
        _write_entity_patch(
            store,
            entity_patch=entity_patch,
            source_chat_ids=_unique_strings(
                [raw_log.id for raw_log in request.raw_logs]
            ),
            reference_time=reference_time,
            profile_bundle=profile_bundle,
        )
        wrote_entity_patches = True

    for section_patch in section_patches:
        section_result = _write_section_timeline(
            store,
            section_patch=section_patch,
            raw_logs=request.raw_logs,
            reference_time=reference_time,
        )
        _update_entity_references(
            store,
            user_id=user_id,
            entity_ids=section_result.entity_ids,
            timeline_id=section_patch.id,
            observed_at=_latest_raw_chat_log_observed_at(raw_logs),
            updated_at=reference_time.isoformat(),
        )
        results.append(section_result)
    return results, wrote_entity_patches


def _write_entity_patch(
    store: IMemoryStore,
    *,
    entity_patch: MemoryEntityPatch,
    source_chat_ids: list[str],
    reference_time: datetime,
    profile_bundle: AgentProfileBundle,
) -> None:
    entity_path = store.entity_path(entity_patch.user_id, entity_patch.id)
    existing_document = _read_existing_entity(
        store,
        entity_path,
        user_id=entity_patch.user_id,
    )
    existing_front_matter = (
        dict(existing_document.front_matter) if existing_document is not None else {}
    )
    existing_properties = _property_dict(
        existing_front_matter.get("properties")
        or existing_front_matter.get("attributes")
        or {}
    )
    patch_properties = _property_dict(entity_patch.properties)
    if entity_patch.id == profile_bundle.relationship_entity_id:
        properties = _relationship_properties(
            existing_properties,
            patch_properties,
            reference_time=reference_time,
            defaults=profile_bundle.relationship_defaults,
        )
        entity_type = profile_bundle.relationship_entity_type
        label = entity_patch.label or profile_bundle.relationship_entity_label
        tags = _unique_strings(
            [
                *front_matter_string_list(existing_front_matter.get("tags", [])),
                "relationship",
                profile_bundle.relationship_tag,
            ]
        )
        importance = 0.75
    else:
        properties = {**existing_properties, **patch_properties}
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
        "attributes": properties,
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


def _relationship_properties(
    existing_properties: dict[str, object],
    patch_properties: dict[str, object],
    *,
    reference_time: datetime,
    defaults: RelationshipDefaults,
) -> dict[str, object]:
    current_trust = _float_value(
        existing_properties.get("trust_score"),
        default=defaults.trust_score,
    )
    current_warmth = _float_value(
        existing_properties.get("warmth_score"),
        default=defaults.warmth_score,
    )
    proposed_trust = _float_value(
        patch_properties.get("trust_score"),
        default=current_trust,
    )
    proposed_warmth = _float_value(
        patch_properties.get("warmth_score"),
        default=current_warmth,
    )
    trust_score = clamp_relationship_score_increase(
        current_score=current_trust,
        proposed_score=proposed_trust,
    )
    warmth_score = clamp_relationship_score_increase(
        current_score=current_warmth,
        proposed_score=proposed_warmth,
    )
    stage = resolve_relationship_stage(
        trust_score=trust_score,
        warmth_score=warmth_score,
    )
    current_stage = _int_value(existing_properties.get("stage"), default=defaults.stage)
    last_stage_changed_at = front_matter_string(
        existing_properties.get("last_stage_changed_at")
    )
    if stage.stage != current_stage:
        last_stage_changed_at = reference_time.isoformat()
    evidence_count = max(
        _int_value(existing_properties.get("evidence_count"), default=0),
        _int_value(patch_properties.get("evidence_count"), default=0),
    )
    recent_signal = front_matter_string(
        patch_properties.get("recent_signal")
        or existing_properties.get("recent_signal")
        or ""
    )
    return {
        **existing_properties,
        **patch_properties,
        "stage": stage.stage,
        "stage_name": stage.name,
        "stage_behavior": stage.behavior,
        "trust_score": trust_score,
        "warmth_score": warmth_score,
        "max_daily_score_increase": MAX_DAILY_SCORE_INCREASE,
        "last_stage_changed_at": last_stage_changed_at or None,
        "evidence_count": evidence_count,
        "recent_signal": recent_signal,
    }


def _write_section_timeline(
    store: IMemoryStore,
    *,
    section_patch: MemoryTimelineSectionPatch,
    raw_logs: list[MemorySleepChatLog],
    reference_time: datetime,
) -> SectionConsolidationResult:
    day = datetime.fromisoformat(section_patch.day).date()
    section_path = store.section_timeline_path(
        user_id=section_patch.user_id,
        day=day,
        section_slug=section_patch.section_slug,
    )
    existing_section = _read_existing_section(
        store,
        section_path,
        user_id=section_patch.user_id,
    )
    summary_of = _unique_strings(raw_log.id for raw_log in raw_logs)
    body = _build_semantic_section_body(
        day=day,
        title=section_patch.title,
        summary=section_patch.summary,
    )
    entity_ids = _unique_strings(section_patch.entity_ids)
    front_matter = _section_front_matter(
        existing_section,
        user_id=section_patch.user_id,
        section_id=section_patch.id,
        day=day,
        section_slug=section_patch.section_slug,
        title=section_patch.title,
        summary_of=summary_of,
        entity_ids=entity_ids,
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
        label = front_matter_string(document.front_matter.get("label"))
        if label:
            labels.append(label)
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
    if entity_type == "relationship":
        lines.extend(
            [
                "",
                "## Relationship Stage",
                "",
                f"- stage: {_format_property(properties.get('stage'))}",
                f"- stage_name: {_format_property(properties.get('stage_name'))}",
                f"- trust_score: {_format_property(properties.get('trust_score'))}",
                f"- warmth_score: {_format_property(properties.get('warmth_score'))}",
                f"- recent_signal: {_format_property(properties.get('recent_signal'))}",
            ]
        )
    elif properties:
        lines.extend(["", "## Known Facts", ""])
        for key, value in sorted(properties.items()):
            lines.append(f"- {key}: {_format_property(value)}")
    return "\n".join(lines)


def _timeline_patch_to_section_patch(
    timeline_patch: MemoryTimelinePatch,
    *,
    fallback_slug: str,
) -> MemoryTimelineSectionPatch:
    return MemoryTimelineSectionPatch(
        id=timeline_patch.id,
        user_id=timeline_patch.user_id,
        day=timeline_patch.day,
        section_slug=fallback_slug,
        title="要約",
        summary=timeline_patch.summary,
        entity_ids=list(timeline_patch.entity_ids),
        confidence=float(timeline_patch.confidence),
    )


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
        if front_matter.get("timeline_type") not in {
            "daily_summary",
            "section_summary",
        }:
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
    return {
        "schema_version": 1,
        "memory_type": "timeline",
        "id": section_id,
        "user_id": user_id,
        "timeline_type": "section_summary",
        "kind": "summary",
        "content": content,
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
) -> None:
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


def _latest_raw_chat_log_observed_at(raw_logs: list[RawChatLog]) -> str | None:
    occurred_values = [_raw_chat_log_observed_at(raw_log) for raw_log in raw_logs]
    observed_values = [value for value in occurred_values if value is not None]
    if not observed_values:
        return None
    return max(observed_values).isoformat()


def _raw_chat_log_observed_at(raw_log: RawChatLog) -> datetime | None:
    if raw_log.created_at is None:
        return None
    return _as_utc(raw_log.created_at)


def _raw_chat_log_text(raw_log: RawChatLog) -> str:
    payload = raw_log.message_content.get("payload")
    if isinstance(payload, dict):
        text = payload.get("text")
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


def _int_value(value: object, *, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def _as_utc(value: datetime) -> datetime:
    return (
        value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    )
