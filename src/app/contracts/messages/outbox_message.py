"""Transactional outbox message contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    """Durable application event awaiting broker publication."""

    id: str
    topic: str
    payload: Mapping[str, object]
    created_at: datetime
    attempt_count: int = 0
    claim_token: str = ""
