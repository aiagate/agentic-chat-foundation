"""Transactional writer for generated agent replies."""

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.chat_events import (
    build_reply_ready_payload,
    reply_topic_for,
)
from app.contracts.ports.agent_reply_writer import (
    AgentReplyWriteError,
    AgentReplyWriteRequest,
    IAgentReplyWriter,
)
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.domain.aggregates.chat import DiscordChat, LineChat
from app.domain.value_objects.chat_type import ChatType
from app.domain.value_objects.message_content import MessageContent


class TransactionalAgentReplyWriter(IAgentReplyWriter):
    """Write assistant chat and reply-ready Outbox rows in one transaction."""

    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def write(
        self,
        request: AgentReplyWriteRequest,
    ) -> Result[None, AgentReplyWriteError]:
        match request.chat_type:
            case ChatType.LINE:
                chat = LineChat.create_user_chat(
                    line_user_id=request.user_id,
                    message_content=MessageContent.texts(request.contents),
                )
            case ChatType.DISCORD:
                chat = DiscordChat.create(
                    guild_id=request.guild_id,
                    channel_id=request.channel_id,
                    message_content=MessageContent.texts(request.contents),
                )

        async with self._uow:
            save_result = await self._uow.GetChatRecordRepository().add(
                chat,
                user_id=request.user_id,
                role="assistant",
            )
            if is_err(save_result):
                return Err(AgentReplyWriteError("Failed to save generated content"))

            self._uow.enqueue_event(
                reply_topic_for(request.chat_type),
                build_reply_ready_payload(
                    chat_type=request.chat_type,
                    contents=request.contents,
                    guild_id=(
                        request.guild_id
                        if request.chat_type is ChatType.DISCORD
                        else None
                    ),
                    channel_id=(
                        request.channel_id
                        if request.chat_type is ChatType.DISCORD
                        else None
                    ),
                    user_id=(
                        request.user_id if request.chat_type is ChatType.LINE else None
                    ),
                    agent_envelope=request.agent_context,
                ),
            )
            commit_result = await self._uow.commit()
            if is_err(commit_result):
                return Err(AgentReplyWriteError("Failed to persist generated content"))

        return Ok(None)
