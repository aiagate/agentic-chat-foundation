"""Atomic assistant chat and reply-ready Outbox persistence."""

from dataclasses import dataclass

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.agent_run import AgentRunSnapshot
from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.chat_events import (
    build_reply_ready_payload,
    reply_topic_for,
)
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.domain.aggregates.chat import DiscordChat, LineChat
from app.domain.value_objects.message_content import MessageContent


@dataclass(frozen=True, slots=True)
class AgentReplyPersistenceError(Exception):
    message: str


class AgentReplyPersistence:
    """Write a generated reply inside the caller's active UoW transaction."""

    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def write(
        self,
        *,
        run: AgentRunSnapshot,
        contents: list[str],
        tool_call_id: str | None = None,
    ) -> Result[None, AgentReplyPersistenceError]:
        if run.chat_type.value == "LINE":
            chat = LineChat.create_user_chat(
                line_user_id=run.user_id,
                message_content=MessageContent.texts(contents),
            )
        else:
            chat = DiscordChat.create(
                guild_id=run.guild_id,
                channel_id=run.channel_id,
                message_content=MessageContent.texts(contents),
            )
        saved = await self._uow.GetChatRecordRepository().add(
            chat, user_id=run.user_id, role="assistant"
        )
        if is_err(saved):
            return Err(AgentReplyPersistenceError(saved.error.message))
        envelope = AgentEnvelope(
            agent_run_id=run.id,
            agent_turn_id=str(run.turn_number),
            character_id=run.character_id,
            tool_call_id=tool_call_id,
            source_message_id=run.source_chat_id,
        )
        self._uow.enqueue_event(
            reply_topic_for(run.chat_type),
            build_reply_ready_payload(
                chat_type=run.chat_type,
                contents=contents,
                guild_id=run.guild_id if run.chat_type.value == "DISCORD" else None,
                channel_id=(
                    run.channel_id if run.chat_type.value == "DISCORD" else None
                ),
                user_id=run.user_id if run.chat_type.value == "LINE" else None,
                agent_envelope=envelope,
            ),
        )
        return Ok(None)
