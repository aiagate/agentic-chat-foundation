"""Agent inference context assembly service."""

import logging

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.llm_request_context import (
    LLMRequestContext,
    build_agent_current_input,
    build_agent_system_prompt,
)
from app.contracts.ports.agent_inference_context import (
    AgentInferenceContextError,
    AgentInferenceContextRequest,
    IAgentInferenceContextService,
)
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.tool_catalog import IToolCatalog
from app.contracts.ports.tool_result_store import IToolResultStore

logger = logging.getLogger(__name__)


class AgentInferenceContextService(IAgentInferenceContextService):
    """Gather memory, profile, tool state, and available tool definitions."""

    def __init__(
        self,
        memory_service: IMemoryService,
        agent_profile_service: IAgentProfileService,
        tool_result_store: IToolResultStore,
        tool_catalog: IToolCatalog,
    ) -> None:
        self._memory_service = memory_service
        self._agent_profile_service = agent_profile_service
        self._tool_result_store = tool_result_store
        self._tool_catalog = tool_catalog

    async def assemble(
        self,
        request: AgentInferenceContextRequest,
    ) -> Result[LLMRequestContext, AgentInferenceContextError]:
        memory_result = await self._memory_service.build_context(request.user_id)
        if is_err(memory_result):
            return Err(AgentInferenceContextError("Failed to retrieve memory context"))

        profile_bundle = self._agent_profile_service.load_agent_profile_bundle()
        tool_result = None
        if request.tool_call_id is not None:
            tool_result_result = await self._tool_result_store.get(
                request.tool_call_id,
                character_id=request.character_id,
            )
            if is_err(tool_result_result):
                logger.warning(
                    "Tool result unavailable for tool call %s: %s",
                    request.tool_call_id,
                    tool_result_result.error,
                )
            else:
                tool_result = tool_result_result.value

        allowed_tool_names = {"memory.read", "memory.write_candidate", "web_search"}
        if request.chat_type is ChatType.LINE:
            allowed_tool_names.add("line.send")
        else:
            allowed_tool_names.add("discord.send")
        tool_definitions = [
            definition
            for definition in self._tool_catalog.list_tools()
            if definition.name in allowed_tool_names
        ]

        return Ok(
            LLMRequestContext(
                system_prompt=build_agent_system_prompt(
                    profile_bundle.persona_context,
                    request.turn_context.conversation,
                ),
                tool_definitions=tool_definitions,
                memory_context=memory_result.value.assembled_context,
                recent_history=request.turn_context.recent_history,
                current_input=build_agent_current_input(
                    prompt=request.turn_context.prompt,
                    tool_result=tool_result,
                    tool_failure_context=request.tool_failure_context,
                ),
            )
        )
