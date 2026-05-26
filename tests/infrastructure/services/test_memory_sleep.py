"""Tests for deterministic memory sleep/consolidation."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from flow_res import Ok

from app.domain.queries.raw_chat_log_query import IRawChatLogQuery, RawChatLog
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.services.memory_consolidation import (
    DeterministicMemoryConsolidationService,
    consolidate_daily_timeline,
)
from app.infrastructure.services.memory_store import FilesystemMemoryStore


def test_consolidate_daily_timeline_writes_summary_and_updates_sources(
    tmp_path: Path,
) -> None:
    """Pending raw Timeline records should become one deterministic daily summary."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    _write_entity(store, user_id="u1", entity_id="project-x")
    _write_raw(
        store,
        user_id="u1",
        raw_id="raw-1",
        occurred_at="2026-05-18T10:00:00+00:00",
        kind="user",
        content="Discussed Project X memory consolidation.",
        importance=0.2,
        entity_ids=["project-x"],
    )
    _write_raw(
        store,
        user_id="u1",
        raw_id="raw-2",
        occurred_at="2026-05-18T11:00:00+00:00",
        kind="assistant",
        content="Outlined deterministic daily summaries.",
        importance=0.8,
        entity_ids=["project-x"],
    )

    result = DeterministicMemoryConsolidationService().consolidate_daily_timeline(
        store,
        user_id="u1",
        day=date(2026, 5, 18),
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )

    daily = store.read_document(
        result.daily_path,
        expected_memory_type="timeline",
        expected_user_id="u1",
    )
    raw_1 = store.read_document(
        _raw_path(store, "u1", "2026-05-18", "raw-1"),
        expected_memory_type="timeline",
        expected_user_id="u1",
    )
    raw_2 = store.read_document(
        _raw_path(store, "u1", "2026-05-18", "raw-2"),
        expected_memory_type="timeline",
        expected_user_id="u1",
    )
    entity = store.read_document(
        store.entity_path("u1", "project-x"),
        expected_memory_type="entity",
        expected_user_id="u1",
    )

    assert result.daily_id == "daily:u1:2026-05-18"
    assert result.processed_raw_ids == ["raw-1", "raw-2"]
    assert result.compressed_raw_ids == ["raw-1"]
    assert result.entity_ids == ["project-x"]
    assert daily.front_matter["timeline_type"] == "daily_summary"
    assert daily.front_matter["consolidation_state"] == "complete"
    assert daily.front_matter["summary_of"] == ["raw-1", "raw-2"]
    assert daily.front_matter["entity_ids"] == ["project-x"]
    assert daily.front_matter["source"] == "consolidation"
    assert "- 10:00 user: Discussed Project X memory consolidation." in daily.body
    assert "- raw-1" in daily.body
    assert raw_1.front_matter["consolidation_state"] == "complete"
    assert raw_1.front_matter["retention_state"] == "compressed"
    assert raw_1.front_matter["metadata"] == {
        "consolidated_into": "daily:u1:2026-05-18"
    }
    assert raw_2.front_matter["consolidation_state"] == "complete"
    assert raw_2.front_matter["retention_state"] == "active"
    assert entity.front_matter["referenced_in"] == ["daily:u1:2026-05-18"]
    assert entity.front_matter["last_observed_at"] == "2026-05-18T11:00:00+00:00"


def test_consolidate_daily_timeline_is_idempotent_for_summary_of(
    tmp_path: Path,
) -> None:
    """Repeated sleep runs must not duplicate raw Timeline IDs in summary_of."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    _write_raw(
        store,
        user_id="u1",
        raw_id="raw-1",
        occurred_at="2026-05-18T10:00:00+00:00",
        kind="user",
        content="Remember the markdown schema.",
        importance=0.2,
        entity_ids=[],
    )

    first = consolidate_daily_timeline(
        store,
        user_id="u1",
        day=date(2026, 5, 18),
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )
    second = consolidate_daily_timeline(
        store,
        user_id="u1",
        day=date(2026, 5, 18),
        reference_time=datetime(2026, 5, 20, tzinfo=UTC),
    )
    daily = store.read_document(
        first.daily_path,
        expected_memory_type="timeline",
        expected_user_id="u1",
    )

    assert first.processed_raw_ids == ["raw-1"]
    assert second.processed_raw_ids == []
    assert daily.front_matter["summary_of"] == ["raw-1"]
    assert daily.body.count("- raw-1") == 1


def test_consolidate_daily_timeline_does_not_compress_pinned_raw(
    tmp_path: Path,
) -> None:
    """Pinned raw Timeline records should complete without retention compression."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    _write_raw(
        store,
        user_id="u1",
        raw_id="raw-pinned",
        occurred_at="2026-05-18T10:00:00+00:00",
        kind="user",
        content="Pinned detail should stay active.",
        importance=0.1,
        entity_ids=[],
        pinned=True,
    )

    result = consolidate_daily_timeline(
        store,
        user_id="u1",
        day=date(2026, 5, 18),
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )
    raw = store.read_document(
        _raw_path(store, "u1", "2026-05-18", "raw-pinned"),
        expected_memory_type="timeline",
        expected_user_id="u1",
    )

    assert result.compressed_raw_ids == []
    assert raw.front_matter["consolidation_state"] == "complete"
    assert raw.front_matter["retention_state"] == "active"


@pytest.mark.anyio
async def test_run_memory_sleep_consolidates_sql_raw_logs_only_for_past_days(
    mocker: Any,
    tmp_path: Path,
) -> None:
    """Scheduled sleep should use SQL raw logs and skip same-day messages."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    _write_entity(store, user_id="u1", entity_id="project-x")

    raw_logs = [
        _raw_chat_log(
            "raw-yesterday-discord",
            user_id="u1",
            role="user",
            chat_type=ChatType.DISCORD,
            created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
            text="Yesterday should be consolidated.",
            entity_ids=["project-x"],
        ),
        _raw_chat_log(
            "raw-yesterday-line",
            user_id="u1",
            role="assistant",
            chat_type=ChatType.LINE,
            created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
            text="Daily summary should include raw SQL logs.",
        ),
        _raw_chat_log(
            "raw-today-discord",
            user_id="u1",
            role="user",
            chat_type=ChatType.DISCORD,
            created_at=datetime(2026, 5, 19, 10, 0, tzinfo=UTC),
            text="Today should remain pending.",
        ),
    ]

    raw_chat_log_query = mocker.Mock(spec=IRawChatLogQuery)
    raw_chat_log_query.list_raw_chat_log_user_ids = AsyncMock(return_value=Ok(["u1"]))
    run_repository = mocker.Mock()
    run_repository.set_run_result = AsyncMock(return_value=Ok(None))
    run_key = "memory-sleep:2026-05-19"
    started_at = datetime(2026, 5, 19, 0, 0, tzinfo=UTC)

    async def _get_raw_chat_logs(
        user_id: str,
        chat_type: ChatType,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 10000,
    ) -> object:
        del since, limit
        assert user_id == "u1"
        assert until is not None
        return Ok(
            [
                raw_log
                for raw_log in raw_logs
                if raw_log.user_id == user_id
                and raw_log.chat_type is chat_type
                and raw_log.created_at is not None
                and raw_log.created_at < until
            ]
        )

    raw_chat_log_query.get_raw_chat_logs = AsyncMock(side_effect=_get_raw_chat_logs)

    consolidated_count = (
        await DeterministicMemoryConsolidationService().run_memory_sleep(
            store,
            run_key=run_key,
            started_at=started_at,
            raw_chat_log_query=raw_chat_log_query,
            run_repository=run_repository,
            reference_time=datetime(2026, 5, 19, tzinfo=UTC),
        )
    )
    yesterday_daily = store.read_document(
        store.daily_timeline_path(user_id="u1", day=date(2026, 5, 18)),
        expected_memory_type="timeline",
        expected_user_id="u1",
    )
    entity = store.read_document(
        store.entity_path("u1", "project-x"),
        expected_memory_type="entity",
        expected_user_id="u1",
    )

    assert consolidated_count == 1
    assert yesterday_daily.front_matter["summary_of"] == [
        "raw-yesterday-discord",
        "raw-yesterday-line",
    ]
    assert "- 10:00 user: Yesterday should be consolidated." in yesterday_daily.body
    assert "- 11:00 assistant: Daily summary should include raw SQL logs." in (
        yesterday_daily.body
    )
    assert entity.front_matter["referenced_in"] == ["daily:u1:2026-05-18"]
    assert entity.front_matter["last_observed_at"] == "2026-05-18T11:00:00+00:00"
    assert raw_chat_log_query.list_raw_chat_log_user_ids.await_count == 1
    assert raw_chat_log_query.get_raw_chat_logs.await_count == 2
    run_repository.set_run_result.assert_awaited_once()
    finalize_args = run_repository.set_run_result.await_args
    assert finalize_args is not None
    assert finalize_args.kwargs["run_key"] == run_key
    assert finalize_args.kwargs["status"] == "complete"


@pytest.mark.anyio
async def test_run_memory_sleep_marks_skipped_when_no_targets(
    mocker: Any,
    tmp_path: Path,
) -> None:
    """Scheduled sleep should mark skipped when there is nothing to process."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    raw_chat_log_query = mocker.Mock(spec=IRawChatLogQuery)
    raw_chat_log_query.list_raw_chat_log_user_ids = AsyncMock(return_value=Ok([]))
    raw_chat_log_query.get_raw_chat_logs = AsyncMock()
    run_repository = mocker.Mock()
    run_repository.set_run_result = AsyncMock(return_value=Ok(None))

    consolidated_count = (
        await DeterministicMemoryConsolidationService().run_memory_sleep(
            store,
            run_key="memory-sleep:2026-05-19",
            started_at=datetime(2026, 5, 19, 0, 0, tzinfo=UTC),
            raw_chat_log_query=raw_chat_log_query,
            run_repository=run_repository,
            reference_time=datetime(2026, 5, 19, tzinfo=UTC),
        )
    )

    assert consolidated_count == 0
    run_repository.set_run_result.assert_awaited_once()
    finalize_args = run_repository.set_run_result.await_args
    assert finalize_args is not None
    assert finalize_args.kwargs["status"] == "skipped"


@pytest.mark.anyio
async def test_run_memory_sleep_marks_failed_when_query_errors(
    mocker: Any,
    tmp_path: Path,
) -> None:
    """Scheduled sleep should keep a failed run record when the query breaks."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    raw_chat_log_query = mocker.Mock(spec=IRawChatLogQuery)
    raw_chat_log_query.list_raw_chat_log_user_ids = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    raw_chat_log_query.get_raw_chat_logs = AsyncMock()
    run_repository = mocker.Mock()
    run_repository.set_run_result = AsyncMock(return_value=Ok(None))

    with pytest.raises(RuntimeError, match="boom"):
        await DeterministicMemoryConsolidationService().run_memory_sleep(
            store,
            run_key="memory-sleep:2026-05-19",
            started_at=datetime(2026, 5, 19, 0, 0, tzinfo=UTC),
            raw_chat_log_query=raw_chat_log_query,
            run_repository=run_repository,
            reference_time=datetime(2026, 5, 19, tzinfo=UTC),
        )

    run_repository.set_run_result.assert_awaited_once()
    finalize_args = run_repository.set_run_result.await_args
    assert finalize_args is not None
    assert finalize_args.kwargs["status"] == "failed"


def _write_raw(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
    raw_id: str,
    occurred_at: str,
    kind: str,
    content: str,
    importance: float,
    entity_ids: list[str],
    pinned: bool = False,
) -> None:
    day = occurred_at[:10]
    store.write_document(
        _raw_path(store, user_id, day, raw_id),
        front_matter={
            "schema_version": 1,
            "memory_type": "timeline",
            "id": raw_id,
            "user_id": user_id,
            "timeline_type": "raw",
            "kind": kind,
            "content": content,
            "occurred_at": occurred_at,
            "source": "chat",
            "entity_ids": entity_ids,
            "summary_of": [],
            "consolidation_state": "pending",
            "retention_state": "active",
            "last_accessed_at": None,
            "access_count": 0,
            "decay_score": 1.0,
            "created_at": occurred_at,
            "updated_at": occurred_at,
            "tags": [],
            "importance": importance,
            "confidence": 1.0,
            "pinned": pinned,
            "metadata": {},
        },
        body=f"# {kind.title()} memory\n\n{content}",
    )


def _write_entity(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
    entity_id: str,
) -> None:
    store.write_document(
        store.entity_path(user_id, entity_id),
        front_matter={
            "schema_version": 1,
            "memory_type": "entity",
            "id": entity_id,
            "user_id": user_id,
            "label": "Project X",
            "entity_type": "project",
            "status": "active",
            "aliases": [],
            "properties": {},
            "attributes": {},
            "missing_attributes": [],
            "referenced_in": [],
            "created_at": "2026-05-18T00:00:00+00:00",
            "updated_at": "2026-05-18T00:00:00+00:00",
            "tags": [],
            "importance": 0.6,
            "confidence": 1.0,
            "pinned": False,
            "metadata": {},
        },
        body="# Project X",
    )


def _raw_chat_log(
    log_id: str,
    *,
    user_id: str,
    role: str,
    chat_type: ChatType,
    created_at: datetime,
    text: str,
    entity_ids: list[str] | None = None,
) -> RawChatLog:
    payload: dict[str, object] = {"text": text}
    if entity_ids is not None:
        payload["entity_ids"] = entity_ids
    return RawChatLog(
        id=log_id,
        user_id=user_id,
        role=role,
        chat_type=chat_type,
        message_content={"type": "TEXT", "payload": payload},
        created_at=created_at,
    )


def _raw_path(
    store: FilesystemMemoryStore,
    user_id: str,
    day: str,
    raw_id: str,
) -> Path:
    year, month, _ = day.split("-")
    return store.root / "timeline" / user_id / "raw" / year / month / f"{raw_id}.md"
