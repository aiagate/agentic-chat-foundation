"""Transactional outbox delivery store boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from flow_res import Result

from app.contracts.messages.outbox_message import OutboxMessage


@dataclass
class OutboxStoreError(Exception):
    """Failure while claiming or updating outbox messages."""

    message: str

    def __str__(self) -> str:
        return self.message


class IOutboxStore(ABC):
    """Claim and update durable outbox messages."""

    @abstractmethod
    async def claim_pending(
        self,
        *,
        limit: int,
        now: datetime,
    ) -> Result[list[OutboxMessage], OutboxStoreError]:
        """Claim a batch of messages for exclusive delivery."""
        raise NotImplementedError

    @abstractmethod
    async def mark_published(
        self,
        message_id: str,
        claim_token: str,
        *,
        published_at: datetime,
    ) -> Result[None, OutboxStoreError]:
        """Mark a claimed message as published."""
        raise NotImplementedError

    @abstractmethod
    async def mark_failed(
        self,
        message_id: str,
        claim_token: str,
        *,
        error: str,
        next_attempt_at: datetime,
    ) -> Result[None, OutboxStoreError]:
        """Release a failed message for a later retry."""
        raise NotImplementedError
