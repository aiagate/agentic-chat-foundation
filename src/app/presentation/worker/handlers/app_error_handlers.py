"""Observational handler for application errors."""

import logging
from collections.abc import Mapping

from app.contracts.messages.app_error import APP_ERROR_DETECTED_TOPIC
from app.presentation.worker.event_payloads import (
    AppErrorDetectedPayload,
    parse_worker_event_payload,
)
from app.presentation.worker.registry import event_handler

logger = logging.getLogger(__name__)


@event_handler(APP_ERROR_DETECTED_TOPIC)
async def on_app_error_detected(payload: Mapping[str, object]) -> None:
    """Log observed errors; durable state transitions own retry decisions."""
    event = parse_worker_event_payload(
        AppErrorDetectedPayload, payload, event_name="App error detected"
    )
    if event is not None:
        logger.warning(
            "Observed application error: operation=%s code=%s message=%s",
            event.operation,
            event.error_code,
            event.message,
        )
