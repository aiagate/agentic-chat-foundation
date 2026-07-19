"""Conversation history adapter for the channel-independent intake use case."""

from datetime import UTC

from flow_res import is_err

from app.contracts.messages.conversation import (
    AcceptedMessage,
    ConversationResult,
    IncomingMessage,
)
from app.contracts.ports.conversation import ConversationHistory
from app.contracts.ports.unit_of_work import IUnitOfWorkFactory
from app.domain.value_objects.conversation_scope import ConversationScope


class SQLAlchemyConversationHistory(ConversationHistory):
    """Persist the canonical incoming and delivered assistant messages."""

    def __init__(self, uow_factory: IUnitOfWorkFactory, character_id: str) -> None:
        self._uow_factory = uow_factory
        self._character_id = character_id

    async def append(
        self, message: IncomingMessage, *, user_id: str
    ) -> AcceptedMessage:
        scope = ConversationScope(
            user_id=user_id,
            character_id=self._character_id,
            channel=message.channel,
            external_conversation_id=message.external_conversation_id,
        )

        occurred_at = message.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        metadata = dict(message.metadata)

        async with self._uow_factory.create() as uow:
            repository = uow.GetChatRecordRepository()
            external_id = (message.external_message_id or "").strip()
            if external_id:
                existing = await repository.find_by_external_message_id(
                    channel=scope.channel,
                    external_message_id=external_id,
                )
                if is_err(existing):
                    raise RuntimeError(existing.error.message)
                if existing.value is not None:
                    if existing.value.user_id != scope.user_id:
                        raise ValueError(
                            "External message id is already owned by another user"
                        )
                    return AcceptedMessage(
                        message_id=existing.value.message_id,
                        character_id=scope.character_id,
                        user_id=existing.value.user_id,
                        external_conversation_id=scope.external_conversation_id,
                        external_participant_id=message.external_participant_id,
                        text=message.text,
                        channel=scope.channel,
                        occurred_at=occurred_at,
                        order_key=existing.value.order_key,
                        metadata=metadata,
                        is_new=False,
                    )

            added = await repository.add_message(
                character_id=scope.character_id,
                channel=scope.channel,
                user_id=scope.user_id,
                external_conversation_id=scope.external_conversation_id,
                external_participant_id=message.external_participant_id,
                external_message_id=external_id or None,
                role="user",
                message_content={
                    "type": "TEXT",
                    "payload": {"texts": [message.text]},
                },
                channel_metadata=metadata,
            )
            if is_err(added):
                raise RuntimeError(added.error.message)
            committed = await uow.commit()
            if is_err(committed):
                raise RuntimeError(committed.error.message)
            if not added.value.is_new:
                if added.value.user_id != scope.user_id:
                    raise ValueError(
                        "External message id is already owned by another user"
                    )
                return AcceptedMessage(
                    message_id=added.value.message_id,
                    character_id=scope.character_id,
                    user_id=added.value.user_id,
                    external_conversation_id=scope.external_conversation_id,
                    external_participant_id=message.external_participant_id,
                    text=message.text,
                    channel=scope.channel,
                    occurred_at=occurred_at,
                    order_key=added.value.order_key,
                    metadata=metadata,
                    is_new=False,
                )
            return AcceptedMessage(
                message_id=added.value.message_id,
                character_id=scope.character_id,
                user_id=scope.user_id,
                external_conversation_id=scope.external_conversation_id,
                external_participant_id=message.external_participant_id,
                text=message.text,
                channel=scope.channel,
                occurred_at=occurred_at,
                order_key=added.value.order_key,
                metadata=metadata,
            )

    async def append_assistant(
        self,
        message: AcceptedMessage,
        result: ConversationResult,
    ) -> None:
        """Persist an assistant result only after successful delivery."""
        scope = ConversationScope(
            user_id=message.user_id,
            character_id=message.character_id,
            channel=message.channel,
            external_conversation_id=message.external_conversation_id,
        )
        contents = [content.strip() for content in result.contents if content.strip()]
        if not contents and result.unavailable and result.failure_reason:
            contents = [result.failure_reason.strip()]
        if not contents:
            raise ValueError("Assistant response has no text content")

        async with self._uow_factory.create() as uow:
            added = await uow.GetChatRecordRepository().add_message(
                character_id=scope.character_id,
                channel=scope.channel,
                user_id=scope.user_id,
                external_conversation_id=scope.external_conversation_id,
                external_participant_id=message.external_participant_id,
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
            committed = await uow.commit()
            if is_err(committed):
                raise RuntimeError(committed.error.message)
