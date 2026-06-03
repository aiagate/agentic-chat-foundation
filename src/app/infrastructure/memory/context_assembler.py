"""Prompt-ready context frame assembly for memory search results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.contracts.messages.memory_context import (
    MemoryContextFrame,
    MemoryFrameSection,
    MemoryFrameSectionName,
    MemorySource,
)
from app.contracts.messages.memory_index import MemorySearchResult
from app.contracts.messages.relationship_growth import RELATIONSHIP_ENTITY_TYPE
from app.infrastructure.memory.markdown import (
    front_matter_string,
    front_matter_string_list,
)

_SECTION_ORDER: tuple[MemoryFrameSectionName, ...] = (
    "primary",
    "functional",
    "peripheral",
)


@dataclass(frozen=True, slots=True)
class _FrameEntry:
    section: MemoryFrameSectionName
    source: MemorySource
    text: str
    score: float


def assemble_context_frame(
    results: Sequence[MemorySearchResult],
    *,
    max_chars: int = 6_000,
) -> MemoryContextFrame:
    """Assemble ordered memory sections into prompt-ready text."""

    entries = sorted(
        (_entry_from_result(result) for result in results),
        key=lambda entry: (entry.section != "primary", -entry.score),
    )
    selected = _select_entries(entries, max_chars=max_chars)
    sections = [
        _section_from_entries(section_name, selected)
        for section_name in _SECTION_ORDER
        if any(entry.section == section_name for entry in selected)
    ]
    assembled_context = _assemble_text(sections)
    return MemoryContextFrame(
        sections=sections,
        assembled_context=assembled_context,
    )


def _entry_from_result(result: MemorySearchResult) -> _FrameEntry:
    front_matter = result.document.document.front_matter
    section = _section_name(front_matter, result.hit.score, result.hit.matched_terms)
    return _FrameEntry(
        section=section,
        source=result.hit.source,
        text=_source_text(
            front_matter,
            body=result.document.document.body,
            reference=result.hit.source.reference,
            score=result.hit.score,
        ),
        score=result.hit.score,
    )


def _section_name(
    front_matter: Mapping[str, object],
    score: float,
    matched_terms: list[str],
) -> MemoryFrameSectionName:
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        if front_matter.get("profile_scope") == "agent":
            return "functional"
        if matched_terms and score >= 1.0:
            return "primary"
        return "functional"
    if memory_type == "entity":
        if front_matter.get("entity_type") == RELATIONSHIP_ENTITY_TYPE:
            return "functional"
        status = front_matter.get("status")
        if status == "unresolved" or front_matter.get("missing_attributes"):
            return "functional"
        if score >= 1.0:
            return "primary"
        return "peripheral"
    if memory_type == "timeline":
        if (
            front_matter.get("timeline_type")
            in {
                "daily_summary",
                "section_summary",
            }
            and score >= 1.0
        ):
            return "primary"
        return "peripheral"
    return "peripheral"


def _source_text(
    front_matter: Mapping[str, object],
    *,
    body: str,
    reference: str | None,
    score: float,
) -> str:
    header = f"## Source: {reference or front_matter_string(front_matter.get('id'))}"
    memory_type = front_matter.get("memory_type")
    lines = [header, f"- memory_type: {memory_type}", f"- score: {score:.3f}"]
    if memory_type == "profile":
        lines.extend(_profile_lines(front_matter))
    elif memory_type == "timeline":
        lines.extend(_timeline_lines(front_matter))
    elif memory_type == "entity":
        lines.extend(_entity_lines(front_matter))

    compact_body = body.strip()
    if compact_body:
        lines.extend(["", compact_body])
    return "\n".join(lines).strip()


def _profile_lines(front_matter: Mapping[str, object]) -> list[str]:
    lines: list[str] = []
    profile_part = front_matter_string(front_matter.get("profile_part"))
    display_name = front_matter_string(front_matter.get("display_name"))
    summary = front_matter_string(front_matter.get("summary"))
    if profile_part:
        lines.append(f"- profile_part: {profile_part}")
    if display_name:
        lines.append(f"- display_name: {display_name}")
    if summary:
        lines.append(f"- summary: {summary}")
    lines.extend(_list_lines("traits", front_matter.get("traits")))
    lines.extend(_list_lines("preferences", front_matter.get("preferences")))
    lines.extend(
        _list_lines("communication_style", front_matter.get("communication_style"))
    )
    lines.extend(
        _list_lines("known_constraints", front_matter.get("known_constraints"))
    )
    return lines


def _timeline_lines(front_matter: Mapping[str, object]) -> list[str]:
    lines = [
        f"- timeline_type: {front_matter_string(front_matter.get('timeline_type'))}",
        f"- kind: {front_matter_string(front_matter.get('kind'))}",
        f"- occurred_at: {front_matter_string(front_matter.get('occurred_at'))}",
        f"- source: {front_matter_string(front_matter.get('source'))}",
    ]
    content = front_matter_string(front_matter.get("content"))
    if content:
        lines.append(f"- content: {content}")
    lines.extend(_list_lines("entity_ids", front_matter.get("entity_ids")))
    return lines


def _entity_lines(front_matter: Mapping[str, object]) -> list[str]:
    lines = [
        f"- id: {front_matter_string(front_matter.get('id'))}",
        f"- label: {front_matter_string(front_matter.get('label'))}",
        f"- entity_type: {front_matter_string(front_matter.get('entity_type'))}",
        f"- status: {front_matter_string(front_matter.get('status'), default='active')}",
    ]
    lines.extend(_list_lines("aliases", front_matter.get("aliases")))
    properties = front_matter.get("properties") or front_matter.get("attributes")
    if isinstance(properties, dict) and properties:
        lines.append("- properties:")
        for key, value in sorted(properties.items()):
            lines.append(f"  - {key}: {_format_value(value)}")
    lines.extend(
        _list_lines("missing_attributes", front_matter.get("missing_attributes"))
    )
    lines.extend(_list_lines("referenced_in", front_matter.get("referenced_in")))
    return lines


def _list_lines(label: str, value: object) -> list[str]:
    values = front_matter_string_list(value)
    if not values:
        return []
    return [f"- {label}: {', '.join(values)}"]


def _format_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value is None:
        return "null"
    return str(value)


def _select_entries(
    entries: Sequence[_FrameEntry],
    *,
    max_chars: int,
) -> list[_FrameEntry]:
    selected: list[_FrameEntry] = []
    for section in _SECTION_ORDER:
        section_entries = sorted(
            (entry for entry in entries if entry.section == section),
            key=lambda entry: entry.score,
            reverse=True,
        )
        for entry in section_entries:
            candidate = [*selected, entry]
            if len(_assemble_text_from_entries(candidate)) <= max_chars:
                selected.append(entry)
                continue
            if section == "primary" and not selected:
                selected.append(
                    _FrameEntry(
                        section=entry.section,
                        source=entry.source,
                        text=entry.text[: max(max_chars - 64, 0)].rstrip(),
                        score=entry.score,
                    )
                )
    return selected


def _section_from_entries(
    section_name: MemoryFrameSectionName,
    entries: Sequence[_FrameEntry],
) -> MemoryFrameSection:
    section_entries = [entry for entry in entries if entry.section == section_name]
    return MemoryFrameSection(
        name=section_name,
        content="\n\n".join(entry.text for entry in section_entries),
        sources=[entry.source for entry in section_entries],
    )


def _assemble_text(sections: Sequence[MemoryFrameSection]) -> str:
    parts = ["Memory Context:"]
    for section in sections:
        parts.append(f"# {section.name.title()}")
        parts.append(section.content)
    return "\n\n".join(parts).strip()


def _assemble_text_from_entries(entries: Sequence[_FrameEntry]) -> str:
    sections = [
        _section_from_entries(section_name, entries)
        for section_name in _SECTION_ORDER
        if any(entry.section == section_name for entry in entries)
    ]
    return _assemble_text(sections)
