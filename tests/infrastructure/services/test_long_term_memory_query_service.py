"""Tests for the long-term memory query service."""

from datetime import UTC, datetime
from typing import Any

import pytest
from flow_res import Err, Ok

from app.domain.queries.raw_chat_log_query import LongTermMemorySourceItem
from app.domain.repositories import RepositoryError, RepositoryErrorType
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.queries.long_term_memory_query_service import (
    LongTermMemoryQueryService,
)


@pytest.mark.anyio
async def test_list_pending_targets_groups_by_day_and_sorts_logs(
    mocker: Any,
) -> None:
    """Pending targets should be grouped per user/day with stable ordering."""

    query = mocker.Mock()
    query.list_pending_memory_user_ids = mocker.AsyncMock(return_value=Ok(["u1"]))
    query.get_pending_memory_source_items = mocker.AsyncMock(
        side_effect=[
            Ok(
                [
                    _long_term_memory_source_item(
                        "raw-b",
                        chat_type=ChatType.DISCORD,
                        created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
                    ),
                    _long_term_memory_source_item(
                        "raw-a",
                        chat_type=ChatType.DISCORD,
                        created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
                    ),
                ]
            ),
            Ok(
                [
                    _long_term_memory_source_item(
                        "raw-c",
                        chat_type=ChatType.LINE,
                        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=UTC),
                    ),
                    _long_term_memory_source_item(
                        "raw-today",
                        chat_type=ChatType.LINE,
                        created_at=datetime(2026, 5, 19, 10, 0, tzinfo=UTC),
                    ),
                ]
            ),
        ]
    )

    service = LongTermMemoryQueryService()
    targets = await service.list_pending_targets(
        query,
        reference_time=datetime(2026, 5, 19, 9, 0, tzinfo=UTC),
    )

    assert len(targets) == 1
    assert targets[0].user_id == "u1"
    assert targets[0].day == datetime(2026, 5, 18).date()
    assert [raw_log.id for raw_log in targets[0].raw_logs] == [
        "raw-a",
        "raw-b",
        "raw-c",
    ]
    query.list_pending_memory_user_ids.assert_awaited_once_with(
        until=datetime(2026, 5, 19, 0, 0, tzinfo=UTC),
        limit=10000,
    )
    assert query.get_pending_memory_source_items.await_count == 2


@pytest.mark.anyio
async def test_list_pending_targets_raises_on_repository_error(
    mocker: Any,
) -> None:
    """Repository failures should surface as runtime errors."""

    query = mocker.Mock()
    query.list_pending_memory_user_ids = mocker.AsyncMock(
        return_value=Err(
            RepositoryError(
                type=RepositoryErrorType.UNEXPECTED,
                message="boom",
            )
        )
    )

    service = LongTermMemoryQueryService()

    with pytest.raises(RuntimeError, match="boom"):
        await service.list_pending_targets(
            query,
            reference_time=datetime(2026, 5, 19, tzinfo=UTC),
        )


def _long_term_memory_source_item(
    raw_id: str,
    *,
    chat_type: ChatType,
    created_at: datetime,
) -> LongTermMemorySourceItem:
    return LongTermMemorySourceItem(
        id=raw_id,
        user_id="u1",
        role="user",
        chat_type=chat_type,
        message_content={"payload": {"text": raw_id}},
        created_at=created_at,
    )
