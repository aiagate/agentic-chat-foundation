"""Publish pending transactional outbox messages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.outbox_store import IOutboxStore


@dataclass(frozen=True, slots=True)
class DispatchOutboxMessagesResult:
    """Summary of one outbox dispatch batch."""

    published_count: int
    failed_count: int


@dataclass(frozen=True, slots=True)
class DispatchOutboxMessagesCommand(
    Request[Result[DispatchOutboxMessagesResult, UseCaseError]]
):
    """Dispatch one bounded batch of pending outbox messages."""

    batch_size: int = 100
    reference_time: datetime | None = None


class DispatchOutboxMessagesHandler(
    RequestHandler[
        DispatchOutboxMessagesCommand,
        Result[DispatchOutboxMessagesResult, UseCaseError],
    ]
):
    """Publish claimed messages and record delivery outcomes."""

    @inject
    def __init__(self, outbox_store: IOutboxStore, event_bus: IEventBus) -> None:
        self._outbox_store = outbox_store
        self._event_bus = event_bus

    async def handle(
        self,
        request: DispatchOutboxMessagesCommand,
    ) -> Result[DispatchOutboxMessagesResult, UseCaseError]:
        if request.batch_size <= 0:
            return Err(
                UseCaseError(
                    type=ErrorType.VALIDATION_ERROR,
                    message="Outbox batch size must be positive",
                )
            )
        now = request.reference_time or datetime.now(UTC)
        claim_result = await self._outbox_store.claim_pending(
            limit=request.batch_size,
            now=now,
        )
        if is_err(claim_result):
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=claim_result.error.message,
                )
            )

        published_count = 0
        failed_count = 0
        for message in claim_result.value:
            try:
                await self._event_bus.publish(message.topic, message.payload)
            except Exception as exc:
                failed_count += 1
                delay_seconds = min(300, 2 ** min(message.attempt_count, 8))
                await self._outbox_store.mark_failed(
                    message.id,
                    message.claim_token,
                    error=str(exc),
                    next_attempt_at=now + timedelta(seconds=delay_seconds),
                )
                continue

            mark_result = await self._outbox_store.mark_published(
                message.id,
                message.claim_token,
                published_at=now,
            )
            if is_err(mark_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=mark_result.error.message,
                    )
                )
            published_count += 1

        return Ok(
            DispatchOutboxMessagesResult(
                published_count=published_count,
                failed_count=failed_count,
            )
        )
