"""Query service for selecting memory sleep targets."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from flow_res import Result, is_err

from app.domain.queries.memory_sleep_query import (
    IMemorySleepQuery,
    MemorySleepTarget,
)
from app.domain.queries.raw_chat_log_query import IRawChatLogQuery, RawChatLog
from app.domain.value_objects.chat_type import ChatType


class MemorySleepQueryService(IMemorySleepQuery):
    """Resolve pending memory sleep targets from raw chat logs."""

    async def list_pending_targets(
        self,
        query: IRawChatLogQuery,
        *,
        reference_time: datetime,
    ) -> list[MemorySleepTarget]:
        """Return user/day batches that should be consolidated."""

        cutoff_day = _as_utc(reference_time).date()
        cutoff_start = datetime.combine(cutoff_day, time.min, tzinfo=UTC)
        user_ids = _require_repository_result(
            await query.list_memory_sleep_source_user_ids(
                until=cutoff_start,
                limit=10000,
            )
        )

        targets: list[MemorySleepTarget] = []
        for user_id in user_ids:
            raw_logs = await self._load_user_raw_chat_logs(
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
                targets.append(
                    MemorySleepTarget(
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
        user_id: str,
        until: datetime,
    ) -> list[RawChatLog]:
        raw_logs: list[RawChatLog] = []
        for chat_type in (ChatType.DISCORD, ChatType.LINE):
            result = await query.get_memory_sleep_source_items(
                user_id,
                chat_type,
                until=until,
                limit=10000,
            )
            raw_logs.extend(_require_repository_result(result))
        return sorted(raw_logs, key=_raw_chat_log_sort_key)


def _raw_chat_log_sort_key(raw_log: RawChatLog) -> tuple[str, str]:
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
