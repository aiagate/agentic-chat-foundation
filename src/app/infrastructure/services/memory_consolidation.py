"""Deterministic sleep/consolidation for Markdown Timeline memories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path

from flow_res import Result, is_err

from app.contracts.ports.memory_store import IMemoryStore
from app.domain.queries.raw_chat_log_query import IRawChatLogQuery, RawChatLog
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.services.memory_decay import (
    calculate_decay_score,
    should_compress_after_consolidation,
)
from app.infrastructure.services.memory_markdown import (
    MemoryMarkdownDocument,
    front_matter_float,
    front_matter_string,
    front_matter_string_list,
)


@dataclass(frozen=True, slots=True)
class DailyConsolidationResult:
    """Result metadata for one daily Timeline consolidation run."""

    daily_path: Path
    daily_id: str
    processed_raw_ids: list[str]
    compressed_raw_ids: list[str]
    entity_ids: list[str]


@dataclass(frozen=True, slots=True)
class _RawTimelineDocument:
    path: Path
    document: MemoryMarkdownDocument


@dataclass(frozen=True, slots=True)
class DeterministicMemoryConsolidationService:
    """Deterministic consolidation service for Markdown memory storage."""

    raw_chat_log_query: IRawChatLogQuery | None = None

    def consolidate_daily_timeline(
        self,
        store: IMemoryStore,
        *,
        user_id: str,
        day: date,
        reference_time: datetime | None = None,
    ) -> DailyConsolidationResult:
        """Consolidate pending raw Timeline records into one daily summary."""

        return consolidate_daily_timeline(
            store,
            user_id=user_id,
            day=day,
            reference_time=reference_time,
        )

    async def run_memory_sleep(
        self,
        store: IMemoryStore,
        *,
        reference_time: datetime | None = None,
        raw_chat_log_query: IRawChatLogQuery | None = None,
    ) -> int:
        """Consolidate all pending raw chat logs older than today."""

        now = _as_utc(reference_time or datetime.now(UTC))
        query = raw_chat_log_query or self.raw_chat_log_query
        if query is None:
            raise RuntimeError("raw_chat_log_query is required for memory sleep")

        try:
            pending_targets = await _sql_pending_sleep_targets(
                query,
                reference_time=now,
            )
            consolidated_count = 0
            for user_id, day, raw_logs in pending_targets:
                result = consolidate_daily_chat_logs(
                    store,
                    raw_logs,
                    user_id=user_id,
                    day=day,
                    reference_time=now,
                )
                if result.processed_raw_ids:
                    consolidated_count += 1
            return consolidated_count
        except Exception:
            raise


def consolidate_daily_chat_logs(
    store: IMemoryStore,
    raw_logs: list[RawChatLog],
    *,
    user_id: str,
    day: date,
    reference_time: datetime | None = None,
) -> DailyConsolidationResult:
    """Consolidate SQL raw chat logs into one daily summary."""

    now = _as_utc(reference_time or datetime.now(UTC))
    daily_path = store.daily_timeline_path(user_id=user_id, day=day)
    daily_id = _daily_timeline_id(user_id=user_id, day=day)
    existing_daily = _read_existing_daily(store, daily_path, user_id=user_id)
    existing_summary_of = _unique_strings(
        existing_daily.front_matter.get("summary_of", [])
        if existing_daily is not None
        else []
    )

    sorted_raw_logs = sorted(
        [
            raw_log
            for raw_log in raw_logs
            if raw_log.created_at is not None
            and _as_utc(raw_log.created_at).date() == day
        ],
        key=_raw_chat_log_sort_key,
    )

    pending_raw_logs = [
        raw_log for raw_log in sorted_raw_logs if raw_log.id not in existing_summary_of
    ]
    final_summary_of = _unique_strings(
        [*existing_summary_of, *(raw_log.id for raw_log in pending_raw_logs)]
    )
    summarized_raw_logs = [
        raw_log for raw_log in sorted_raw_logs if raw_log.id in final_summary_of
    ]
    entity_ids = _raw_chat_log_entity_ids(summarized_raw_logs)

    if existing_daily is not None and not pending_raw_logs:
        return DailyConsolidationResult(
            daily_path=daily_path,
            daily_id=daily_id,
            processed_raw_ids=[],
            compressed_raw_ids=[],
            entity_ids=entity_ids,
        )

    if final_summary_of:
        front_matter = _daily_front_matter(
            existing_daily,
            user_id=user_id,
            daily_id=daily_id,
            day=day,
            summary_of=final_summary_of,
            entity_ids=entity_ids,
            content=_daily_content_from_raw_chat_logs(
                summarized_raw_logs,
                day=day,
            ),
            now=now,
        )
        store.write_document(
            daily_path,
            front_matter=front_matter,
            body=_daily_body_from_raw_chat_logs(
                summarized_raw_logs,
                day=day,
                summary_of=final_summary_of,
            ),
        )
        _update_entity_references(
            store,
            user_id=user_id,
            entity_ids=entity_ids,
            timeline_id=daily_id,
            observed_at=_latest_raw_chat_log_observed_at(summarized_raw_logs),
            updated_at=now.isoformat(),
        )

    return DailyConsolidationResult(
        daily_path=daily_path,
        daily_id=daily_id,
        processed_raw_ids=[raw_log.id for raw_log in pending_raw_logs],
        compressed_raw_ids=[],
        entity_ids=entity_ids,
    )


async def _sql_pending_sleep_targets(
    query: IRawChatLogQuery,
    *,
    reference_time: datetime,
) -> list[tuple[str, date, list[RawChatLog]]]:
    cutoff_day = reference_time.date()
    cutoff_start = datetime.combine(cutoff_day, time.min, tzinfo=UTC)
    user_ids_result = await query.list_raw_chat_log_user_ids(
        until=cutoff_start,
        limit=10000,
    )
    user_ids = _require_repository_result(user_ids_result)
    targets: list[tuple[str, date, list[RawChatLog]]] = []
    for user_id in user_ids:
        raw_logs = await _load_user_raw_chat_logs(
            query,
            user_id=user_id,
            until=cutoff_start,
        )
        grouped: dict[date, list[RawChatLog]] = {}
        for raw_log in raw_logs:
            if raw_log.created_at is None:
                continue
            occurred_at = _as_utc(raw_log.created_at)
            if occurred_at.date() >= cutoff_day:
                continue
            grouped.setdefault(occurred_at.date(), []).append(raw_log)

        for day in sorted(grouped):
            grouped[day].sort(key=_raw_chat_log_sort_key)
            targets.append((user_id, day, grouped[day]))
    return targets


async def _load_user_raw_chat_logs(
    query: IRawChatLogQuery,
    *,
    user_id: str,
    until: datetime,
) -> list[RawChatLog]:
    raw_logs: list[RawChatLog] = []
    for chat_type in (ChatType.DISCORD, ChatType.LINE):
        result = await query.get_raw_chat_logs(
            user_id,
            chat_type,
            until=until,
            limit=10000,
        )
        raw_logs.extend(_require_repository_result(result))
    return sorted(raw_logs, key=_raw_chat_log_sort_key)


def _raw_chat_log_sort_key(raw_log: RawChatLog) -> tuple[str, str]:
    occurred_at = _raw_chat_log_observed_at(raw_log)
    occurred_key = occurred_at.isoformat() if occurred_at is not None else ""
    return occurred_key, raw_log.id


def _require_repository_result[T, E: Exception](result: Result[T, E]) -> T:
    if is_err(result):
        error = getattr(result, "error", None)
        raise RuntimeError(str(error) if error is not None else "Query failed")
    return result.value


def _daily_body_from_raw_chat_logs(
    raw_logs: list[RawChatLog],
    *,
    day: date,
    summary_of: list[str],
) -> str:
    lines = ["# Daily summary", "", f"## Summary for {day.isoformat()}", ""]
    if raw_logs:
        lines.extend(_raw_chat_log_summary_lines(raw_logs))
    else:
        lines.append("- No raw chat logs were available for this summary.")
    lines.extend(["", "## Source Timeline IDs", ""])
    lines.extend(f"- {timeline_id}" for timeline_id in summary_of)
    return "\n".join(lines)


def _daily_content_from_raw_chat_logs(
    raw_logs: list[RawChatLog],
    *,
    day: date,
) -> str:
    if not raw_logs:
        return f"Daily summary for {day.isoformat()}."
    return " ".join(_raw_chat_log_summary_lines(raw_logs))


def _raw_chat_log_summary_lines(raw_logs: list[RawChatLog]) -> list[str]:
    lines: list[str] = []
    for raw_log in raw_logs:
        occurred_at = _raw_chat_log_observed_at(raw_log)
        occurred_label = occurred_at.strftime("%H:%M") if occurred_at else "unknown"
        kind = _one_line(raw_log.role or "event")
        content = _one_line(_raw_chat_log_text(raw_log))
        lines.append(f"- {occurred_label} {kind}: {content}")
    return lines


def _raw_chat_log_entity_ids(raw_logs: list[RawChatLog]) -> list[str]:
    entity_ids: list[str] = []
    for raw_log in raw_logs:
        payload = raw_log.message_content.get("payload")
        if not isinstance(payload, dict):
            continue
        raw_entity_ids = payload.get("entity_ids")
        if isinstance(raw_entity_ids, list):
            entity_ids.extend(_unique_strings(raw_entity_ids))
    return _unique_strings(entity_ids)


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


def consolidate_daily_timeline(
    store: IMemoryStore,
    *,
    user_id: str,
    day: date,
    reference_time: datetime | None = None,
) -> DailyConsolidationResult:
    """Consolidate pending raw Timeline records into one daily summary."""

    now = _as_utc(reference_time or datetime.now(UTC))
    daily_path = store.daily_timeline_path(user_id=user_id, day=day)
    daily_id = _daily_timeline_id(user_id=user_id, day=day)
    existing_daily = _read_existing_daily(store, daily_path, user_id=user_id)
    existing_summary_of = _unique_strings(
        existing_daily.front_matter.get("summary_of", [])
        if existing_daily is not None
        else []
    )

    raw_documents = _read_raw_documents_for_day(store, user_id=user_id, day=day)
    pending_documents = [
        item
        for item in raw_documents
        if _timeline_id(item.document) not in existing_summary_of
        and item.document.front_matter.get("consolidation_state") == "pending"
    ]
    already_summarized_pending = [
        item
        for item in raw_documents
        if _timeline_id(item.document) in existing_summary_of
        and item.document.front_matter.get("consolidation_state") == "pending"
    ]

    processed_ids = [_timeline_id(item.document) for item in pending_documents]
    final_summary_of = _unique_strings([*existing_summary_of, *processed_ids])
    summarized_documents = [
        item
        for item in raw_documents
        if _timeline_id(item.document) in final_summary_of
    ]
    entity_ids = _entity_ids(summarized_documents)
    compressed_ids = _update_raw_documents(
        store,
        [*pending_documents, *already_summarized_pending],
        daily_id=daily_id,
        updated_at=now.isoformat(),
        reference_time=now,
    )

    if final_summary_of:
        front_matter = _daily_front_matter(
            existing_daily,
            user_id=user_id,
            daily_id=daily_id,
            day=day,
            summary_of=final_summary_of,
            entity_ids=entity_ids,
            content=_daily_content(summarized_documents, day=day),
            now=now,
        )
        store.write_document(
            daily_path,
            front_matter=front_matter,
            body=_daily_body(
                summarized_documents, day=day, summary_of=final_summary_of
            ),
        )
        _update_entity_references(
            store,
            user_id=user_id,
            entity_ids=entity_ids,
            timeline_id=daily_id,
            observed_at=_latest_observed_at(summarized_documents),
            updated_at=now.isoformat(),
        )

    return DailyConsolidationResult(
        daily_path=daily_path,
        daily_id=daily_id,
        processed_raw_ids=processed_ids,
        compressed_raw_ids=compressed_ids,
        entity_ids=entity_ids,
    )


def _read_existing_daily(
    store: IMemoryStore,
    daily_path: Path,
    *,
    user_id: str,
) -> MemoryMarkdownDocument | None:
    if not daily_path.exists():
        return None
    return store.read_document(
        daily_path,
        expected_memory_type="timeline",
        expected_user_id=user_id,
    )


def _read_raw_documents_for_day(
    store: IMemoryStore,
    *,
    user_id: str,
    day: date,
) -> list[_RawTimelineDocument]:
    raw_documents: list[_RawTimelineDocument] = []
    for path in store.iter_timeline_paths(user_id):
        document = store.read_document(
            path,
            expected_memory_type="timeline",
            expected_user_id=user_id,
        )
        front_matter = document.front_matter
        if front_matter.get("timeline_type") != "raw":
            continue
        if _occurred_date(front_matter.get("occurred_at")) != day:
            continue
        raw_documents.append(_RawTimelineDocument(path=path, document=document))
    return sorted(
        raw_documents,
        key=lambda item: (
            front_matter_string(item.document.front_matter.get("occurred_at")),
            _timeline_id(item.document),
        ),
    )


def _update_raw_documents(
    store: IMemoryStore,
    raw_documents: list[_RawTimelineDocument],
    *,
    daily_id: str,
    updated_at: str,
    reference_time: datetime,
) -> list[str]:
    compressed_ids: list[str] = []
    for item in raw_documents:
        front_matter = dict(item.document.front_matter)
        front_matter["consolidation_state"] = "complete"
        front_matter["updated_at"] = updated_at
        metadata = _metadata(front_matter.get("metadata"))
        metadata["consolidated_into"] = daily_id
        front_matter["metadata"] = metadata
        if should_compress_after_consolidation(front_matter):
            front_matter["retention_state"] = "compressed"
            compressed_ids.append(_timeline_id(item.document))
        front_matter["decay_score"] = calculate_decay_score(
            front_matter,
            reference_time=reference_time,
        )
        store.write_document(
            item.path,
            front_matter=front_matter,
            body=item.document.body,
        )
    return compressed_ids


def _daily_front_matter(
    existing_daily: MemoryMarkdownDocument | None,
    *,
    user_id: str,
    daily_id: str,
    day: date,
    summary_of: list[str],
    entity_ids: list[str],
    content: str,
    now: datetime,
) -> dict[str, object]:
    existing_front_matter = (
        dict(existing_daily.front_matter) if existing_daily is not None else {}
    )
    created_at = front_matter_string(
        existing_front_matter.get("created_at"),
        default=now.isoformat(),
    )
    return {
        "schema_version": 1,
        "memory_type": "timeline",
        "id": daily_id,
        "user_id": user_id,
        "timeline_type": "daily_summary",
        "kind": "summary",
        "content": content,
        "occurred_at": datetime.combine(day, time.min, tzinfo=UTC).isoformat(),
        "source": "consolidation",
        "entity_ids": entity_ids,
        "summary_of": summary_of,
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
                "daily",
                "summary",
            ]
        ),
        "importance": max(
            front_matter_float(existing_front_matter.get("importance"), default=0.0),
            0.6,
        ),
        "confidence": max(
            front_matter_float(existing_front_matter.get("confidence"), default=0.0),
            1.0,
        ),
        "pinned": existing_front_matter.get("pinned") is True,
        "metadata": _metadata(existing_front_matter.get("metadata")),
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


def _daily_body(
    raw_documents: list[_RawTimelineDocument],
    *,
    day: date,
    summary_of: list[str],
) -> str:
    lines = ["# Daily summary", "", f"## Summary for {day.isoformat()}", ""]
    if raw_documents:
        lines.extend(_raw_summary_lines(raw_documents))
    else:
        lines.append("- No raw Timeline records were available for this summary.")
    lines.extend(["", "## Source Timeline IDs", ""])
    lines.extend(f"- {timeline_id}" for timeline_id in summary_of)
    return "\n".join(lines)


def _daily_content(raw_documents: list[_RawTimelineDocument], *, day: date) -> str:
    if not raw_documents:
        return f"Daily summary for {day.isoformat()}."
    return " ".join(_raw_summary_lines(raw_documents))


def _raw_summary_lines(raw_documents: list[_RawTimelineDocument]) -> list[str]:
    lines: list[str] = []
    for item in raw_documents:
        front_matter = item.document.front_matter
        occurred_at = _datetime_value(front_matter.get("occurred_at"))
        occurred_label = occurred_at.strftime("%H:%M") if occurred_at else "unknown"
        kind = front_matter_string(front_matter.get("kind"), default="event")
        content = _one_line(front_matter_string(front_matter.get("content")))
        lines.append(f"- {occurred_label} {kind}: {content}")
    return lines


def _entity_ids(raw_documents: list[_RawTimelineDocument]) -> list[str]:
    entity_ids: list[str] = []
    for item in raw_documents:
        entity_ids.extend(
            front_matter_string_list(item.document.front_matter.get("entity_ids", []))
        )
    return _unique_strings(entity_ids)


def _latest_observed_at(raw_documents: list[_RawTimelineDocument]) -> str | None:
    occurred_values = [
        _datetime_value(item.document.front_matter.get("occurred_at"))
        for item in raw_documents
    ]
    observed_values = [value for value in occurred_values if value is not None]
    if not observed_values:
        return None
    return max(observed_values).isoformat()


def _timeline_id(document: MemoryMarkdownDocument) -> str:
    return front_matter_string(document.front_matter["id"])


def _daily_timeline_id(*, user_id: str, day: date) -> str:
    return f"daily:{user_id}:{day.isoformat()}"


def _occurred_date(value: object) -> date | None:
    parsed = _datetime_value(value)
    if parsed is None:
        return None
    return parsed.date()


def _datetime_value(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if not isinstance(value, str):
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _metadata(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _unique_strings(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        string_value = front_matter_string(value)
        if string_value in seen:
            continue
        seen.add(string_value)
        unique_values.append(string_value)
    return unique_values
