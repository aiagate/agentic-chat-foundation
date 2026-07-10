"""Run a single agent turn with optional retrieved context."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.agentic import AgentEnvelope, with_character_id
from app.contracts.messages.llm_request_context import compose_system_instruction
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.agent_inference_context import (
    AgentInferenceContextRequest,
    IAgentInferenceContextService,
)
from app.contracts.ports.agent_reply_writer import (
    AgentReplyWriteRequest,
    IAgentReplyWriter,
)
from app.contracts.ports.agent_turn_context_query import IAgentTurnContextQuery
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.tool_call_router import (
    IToolCallRouter,
    ToolCallRoutingRequest,
)
from app.domain.value_objects.chat_type import ChatType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunAgentTurnResult:
    """Result metadata for one agent turn."""

    contents: list[str]
    tool_call_id: str | None = None


@dataclass
class RunAgentTurnCommand(Request[Result[RunAgentTurnResult, UseCaseError]]):
    """Run the agent runtime for one turn."""

    chat_id: str
    guild_id: str
    channel_id: str
    character_id: str
    user_id: str = "default"
    chat_type: ChatType = ChatType.DISCORD
    prompt: str | None = None
    source_request_id: str | None = None
    tool_call_id: str | None = None
    tool_failure_context: str | None = None
    agent_context: AgentEnvelope | None = None


class RunAgentTurnHandler(
    RequestHandler[RunAgentTurnCommand, Result[RunAgentTurnResult, UseCaseError]]
):
    """Handle one agent turn and re-enter the search workflow when needed."""

    @inject
    def __init__(
        self,
        ai_service: IAIService,
        agent_turn_context_query: IAgentTurnContextQuery,
        inference_context_service: IAgentInferenceContextService,
        agent_reply_writer: IAgentReplyWriter,
        tool_call_router: IToolCallRouter,
    ) -> None:
        self._ai_service = ai_service
        self._agent_turn_context_query = agent_turn_context_query
        self._inference_context_service = inference_context_service
        self._agent_reply_writer = agent_reply_writer
        self._tool_call_router = tool_call_router

    async def handle(
        self, request: RunAgentTurnCommand
    ) -> Result[RunAgentTurnResult, UseCaseError]:
        """Generate content, execute tool requests, and persist the reply."""

        character_id = request.character_id
        agent_context = with_character_id(request.agent_context, character_id)

        turn_context_result = await self._agent_turn_context_query.load(
            chat_id=request.chat_id,
            provided_prompt=request.prompt,
            chat_type=request.chat_type,
            user_id=request.user_id,
            guild_id=request.guild_id,
            channel_id=request.channel_id,
        )
        if is_err(turn_context_result):
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=turn_context_result.error.message,
                )
            )
        turn_context = turn_context_result.value

        llm_context_result = await self._inference_context_service.assemble(
            AgentInferenceContextRequest(
                turn_context=turn_context,
                user_id=request.user_id,
                character_id=character_id,
                chat_type=request.chat_type,
                tool_call_id=request.tool_call_id,
                tool_failure_context=request.tool_failure_context,
            )
        )
        if is_err(llm_context_result):
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=llm_context_result.error.message,
                )
            )
        llm_context = llm_context_result.value
        logger.info(
            "Structured LLM request context: %s",
            llm_context.model_dump_json(),
        )

        ai_result = await self._ai_service.generate_content(
            llm_context.current_input.content,
            llm_context.recent_history,
            system_instruction=compose_system_instruction(llm_context),
            tool_definitions=llm_context.tool_definitions,
        )
        if is_err(ai_result):
            logger.warning(
                "AI content generation failed: %s",
                ai_result.error.message,
            )
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=(f"Failed to generate content: {ai_result.error.message}"),
                )
            )

        persisted_contents: list[str] = []
        if ai_result.value.contents:
            reply_result = await self._agent_reply_writer.write(
                AgentReplyWriteRequest(
                    chat_type=request.chat_type,
                    guild_id=request.guild_id,
                    channel_id=request.channel_id,
                    user_id=request.user_id,
                    contents=ai_result.value.contents,
                    agent_context=agent_context,
                )
            )
            if is_err(reply_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=reply_result.error.message,
                    )
                )
            persisted_contents = ai_result.value.contents

        if ai_result.value.tool_calls:
            route_result = await self._tool_call_router.route(
                ToolCallRoutingRequest(
                    chat_id=request.chat_id,
                    source_request_id=request.source_request_id or request.chat_id,
                    guild_id=request.guild_id,
                    channel_id=request.channel_id,
                    user_id=request.user_id,
                    chat_type=request.chat_type,
                    tool_calls=ai_result.value.tool_calls,
                    character_id=character_id,
                    agent_context=agent_context,
                )
            )
            if is_err(route_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to route tool request",
                    )
                )
            return Ok(
                RunAgentTurnResult(
                    contents=persisted_contents,
                    tool_call_id=request.tool_call_id,
                )
            )
        return Ok(
            RunAgentTurnResult(
                contents=persisted_contents,
                tool_call_id=request.tool_call_id,
            )
        )
