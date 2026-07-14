"""Conversation history adapter for the channel-independent intake use case."""

from datetime import UTC

from flow_res import is_err

from app.contracts.messages.conversation import (
    AcceptedMessage,
    ConversationResult,
    IncomingMessage,
)
from app.contracts.ports.conversation import ConversationHistory
from app.contracts.ports.unit_of_work import IUnitOfWork


class SQLAlchemyConversationHistory(ConversationHistory):
    """Persist the canonical incoming and delivered assistant messages."""

    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def append(self, message: IncomingMessage) -> AcceptedMessage:
        channel = message.channel.strip().lower()
        if channel not in {"discord", "line"}:
            raise ValueError(f"Unsupported conversation channel: {message.channel}")

        occurred_at = message.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        metadata = dict(message.metadata)

        async with self._uow:
            repository = self._uow.GetChatRecordRepository()
            external_id = (message.external_message_id or "").strip()
            if external_id:
                existing = await repository.find_by_external_message_id(
                    channel=channel,
                    external_message_id=external_id,
                )
                if is_err(existing):
                    raise RuntimeError(existing.error.message)
                if existing.value is not None:
                    return AcceptedMessage(
                        message_id=existing.value,
                        conversation_id=message.external_conversation_id,
                        participant_id=message.external_participant_id,
                        text=message.text,
                        channel=channel,
                        occurred_at=occurred_at,
                        metadata=metadata,
                        is_new=False,
                    )

            added = await repository.add_message(
                channel=channel,
                external_conversation_id=message.external_conversation_id,
                external_participant_id=message.external_participant_id,
                external_message_id=external_id or None,
                role="user",
                message_content={
                    "type": "TEXT",
                    "payload": {"text": message.text},
                },
                channel_metadata=metadata,
            )
            if is_err(added):
                raise RuntimeError(added.error.message)
            committed = await self._uow.commit()
            if is_err(committed):
                raise RuntimeError(committed.error.message)
            return AcceptedMessage(
                message_id=added.value,
                conversation_id=message.external_conversation_id,
                participant_id=message.external_participant_id,
                text=message.text,
                channel=channel,
                occurred_at=occurred_at,
                metadata=metadata,
            )

    async def append_assistant(
        self,
        message: AcceptedMessage,
        result: ConversationResult,
    ) -> None:
        """Persist an assistant result only after successful delivery."""
        contents = [content.strip() for content in result.contents if content.strip()]
        if not contents and result.unavailable and result.failure_reason:
            contents = [result.failure_reason.strip()]
        if not contents:
            raise ValueError("Assistant response has no text content")

        async with self._uow:
            added = await self._uow.GetChatRecordRepository().add_message(
                channel=message.channel.strip().lower(),
                external_conversation_id=message.conversation_id,
                external_participant_id=message.participant_id,
                external_message_id=None,
                role="assistant",
                message_content={
                    "type": "TEXT",
                    "payload": {"texts": contents},
                },
                channel_metadata=dict(message.metadata),
            )
            if is_err(added):
                raise RuntimeError(added.error.message)
            committed = await self._uow.commit()
            if is_err(committed):
                raise RuntimeError(committed.error.message)
