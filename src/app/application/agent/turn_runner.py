"""Run external inference without holding a database transaction."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.agent_run import AgentRunSnapshot
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.llm_request_context import compose_system_instruction
from app.contracts.ports.agent_inference_context import (
    AgentInferenceContextRequest,
    IAgentInferenceContextService,
)
from app.contracts.ports.agent_turn_context_query import IAgentTurnContextQuery
from app.contracts.ports.ai_service import IAIService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentTurnError(Exception):
    """Failure during external context loading or inference."""

    code: str
    message: str


class AgentTurnRunner:
    """Pure application service for one inference turn."""

    def __init__(
        self,
        ai_service: IAIService,
        context_query: IAgentTurnContextQuery,
        inference_context: IAgentInferenceContextService,
    ) -> None:
        self._ai_service = ai_service
        self._context_query = context_query
        self._inference_context = inference_context

    async def run(
        self, run: AgentRunSnapshot
    ) -> Result[GeneratedContent, AgentTurnError]:
        turn_context_result = await self._context_query.load(
            chat_id=run.source_chat_id,
            provided_prompt=None,
            chat_type=run.chat_type,
            user_id=run.user_id,
            guild_id=run.guild_id,
            channel_id=run.channel_id,
        )
        if is_err(turn_context_result):
            return Err(
                AgentTurnError("context_load_failed", turn_context_result.error.message)
            )
        llm_context_result = await self._inference_context.assemble(
            AgentInferenceContextRequest(
                turn_context=turn_context_result.value,
                user_id=run.user_id,
                character_id=run.character_id,
                chat_type=run.chat_type,
                tool_results=tuple(run.tool_results),
            )
        )
        if is_err(llm_context_result):
            return Err(
                AgentTurnError(
                    "context_assembly_failed", llm_context_result.error.message
                )
            )
        context = llm_context_result.value
        logger.info("AgentRun %s turn %s inference", run.id, run.turn_number)
        generated = await self._ai_service.generate_content(
            context.current_input.content,
            context.recent_history,
            system_instruction=compose_system_instruction(context),
            tool_definitions=context.tool_definitions,
        )
        if is_err(generated):
            return Err(AgentTurnError("inference_failed", generated.error.message))
        return Ok(generated.value)
