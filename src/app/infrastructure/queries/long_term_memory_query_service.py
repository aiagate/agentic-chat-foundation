"""Query service for selecting long-term memory organization targets."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from flow_res import Result, is_err

from app.contracts.messages.chat_type import ChatType
from app.domain.queries.long_term_memory_query import (
    ILongTermMemoryQuery,
    LongTermMemoryTarget,
)
from app.domain.queries.raw_chat_log_query import (
    IRawChatLogQuery,
    LongTermMemorySourceItem,
)


class LongTermMemoryQueryService(ILongTermMemoryQuery):
    """Resolve pending organization targets from raw chat logs."""

    async def list_pending_targets(
        self,
        query: IRawChatLogQuery,
        *,
        character_id: str,
        reference_time: datetime,
    ) -> list[LongTermMemoryTarget]:
        """Return user/day batches that should be consolidated."""

        jst = ZoneInfo("Asia/Tokyo")
        cutoff_day = _as_utc(reference_time).astimezone(jst).date()
        cutoff_start_jst = datetime.combine(cutoff_day, time.min, tzinfo=jst)
        cutoff_start = cutoff_start_jst.astimezone(UTC)
        user_ids = _require_repository_result(
            await query.list_pending_memory_user_ids(
                character_id,
                until=cutoff_start,
                limit=10000,
            )
        )

        targets: list[LongTermMemoryTarget] = []
        for user_id in user_ids:
            raw_logs = await self._load_user_raw_chat_logs(
                query,
                character_id=character_id,
                user_id=user_id,
                until=cutoff_start,
            )
            grouped: dict[date, list[LongTermMemorySourceItem]] = {}
            for raw_log in raw_logs:
                if raw_log.created_at is None:
                    continue
                occurred_at = _as_utc(raw_log.created_at).astimezone(jst)
                if occurred_at.date() >= cutoff_day:
                    continue
                grouped.setdefault(occurred_at.date(), []).append(raw_log)

            for day in sorted(grouped):
                grouped[day].sort(key=_raw_chat_log_sort_key)
                targets.append(
                    LongTermMemoryTarget(
                        character_id=character_id,
                        user_id=user_id,
                        day=day,
                        raw_logs=grouped[day],
                    )
                )
        return targets

    async def _load_user_raw_chat_logs(
        self,
        query: IRawChatLogQuery,
        *,
        character_id: str,
        user_id: str,
        until: datetime,
    ) -> list[LongTermMemorySourceItem]:
        raw_logs: list[LongTermMemorySourceItem] = []
        for chat_type in (ChatType.DISCORD, ChatType.LINE):
            result = await query.get_pending_memory_source_items(
                character_id,
                user_id,
                chat_type,
                until=until,
                limit=10000,
            )
            raw_logs.extend(_require_repository_result(result))
        return sorted(raw_logs, key=_raw_chat_log_sort_key)


def _raw_chat_log_sort_key(raw_log: LongTermMemorySourceItem) -> tuple[str, str]:
    occurred_at = raw_log.created_at
    occurred_key = _as_utc(occurred_at).isoformat() if occurred_at is not None else ""
    return occurred_key, raw_log.id


def _require_repository_result[T, E: Exception](result: Result[T, E]) -> T:
    if is_err(result):
        error = getattr(result, "error", None)
        if error is None:
            raise RuntimeError("Query failed")
        message = getattr(error, "message", None)
        raise RuntimeError(str(message) if message is not None else str(error))
    return result.value


def _as_utc(value: datetime) -> datetime:
    return (
        value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    )
