"""Helpers for persisting and publishing one agent-turn reply."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.chat_events import (
    build_reply_ready_payload,
    reply_topic_for,
)
from app.contracts.ports.event_bus import IEventBus
from app.domain.aggregates.chat import DiscordChat, LineChat
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.domain.value_objects.message_content import MessageContent
from app.usecases.result import ErrorType, UseCaseError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PersistedReply:
    """Reply payload ready to be returned from the handler."""

    contents: list[str]
    tool_call_id: str | None


async def persist_reply(
    *,
    uow: IUnitOfWork,
    event_bus: IEventBus,
    chat_type: ChatType,
    guild_id: str,
    channel_id: str,
    user_id: str,
    contents: list[str],
    agent_context: AgentEnvelope,
    tool_call_id: str | None,
) -> Result[PersistedReply, UseCaseError]:
    """Persist the generated reply and publish the ready event."""

    model_chat = build_reply_chat(
        chat_type=chat_type,
        guild_id=guild_id,
        channel_id=channel_id,
        user_id=user_id,
        contents=contents,
    )

    save_result = await _save_generated_chat(
        uow,
        model_chat,
        user_id,
    )
    if is_err(save_result):
        return Err(
            UseCaseError(
                type=ErrorType.UNEXPECTED,
                message="Failed to save generated content",
            )
        )

    commit_result = await uow.commit()
    if is_err(commit_result):
        return Err(
            UseCaseError(
                type=ErrorType.UNEXPECTED,
                message="Failed to persist generated content",
            )
        )

    try:
        await event_bus.publish(
            reply_topic_for(chat_type),
            build_reply_ready_payload(
                chat_type=chat_type,
                contents=contents,
                guild_id=guild_id if chat_type is ChatType.DISCORD else None,
                channel_id=channel_id if chat_type is ChatType.DISCORD else None,
                user_id=user_id if chat_type is ChatType.LINE else None,
                agent_envelope=agent_context,
            ),
        )
    except Exception:
        logger.exception("Failed to publish chat reply event")

    return Ok(PersistedReply(contents=contents, tool_call_id=tool_call_id))


def build_reply_chat(
    *,
    chat_type: ChatType,
    guild_id: str,
    channel_id: str,
    user_id: str,
    contents: list[str],
) -> DiscordChat | LineChat:
    """Build the domain chat aggregate for a generated assistant reply."""

    match chat_type:
        case ChatType.LINE:
            return LineChat.create_user_chat(
                line_user_id=user_id,
                message_content=MessageContent.texts(contents),
            )
        case ChatType.DISCORD:
            return DiscordChat.create(
                guild_id=guild_id,
                channel_id=channel_id,
                message_content=MessageContent.texts(contents),
            )


async def _save_generated_chat(
    uow: IUnitOfWork,
    chat: DiscordChat | LineChat,
    user_id: str,
) -> Result[DiscordChat | LineChat, UseCaseError]:
    """Persist a generated assistant chat as raw SQL."""

    chat_record_repository = uow.GetChatRecordRepository()
    save_result = await chat_record_repository.add(
        chat,
        user_id=user_id,
        role="assistant",
    )
    if is_err(save_result):
        return Err(
            UseCaseError(
                type=ErrorType.UNEXPECTED,
                message="Failed to save generated content",
            )
        )
    return Ok(cast(DiscordChat | LineChat, save_result.value))
