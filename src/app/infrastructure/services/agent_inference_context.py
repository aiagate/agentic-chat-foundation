"""Agent inference context assembly service."""

import logging

from flow_res import Err, Ok, Result, is_err

from app.application.relationship import (
    render_relationship_behavior,
    select_relationship_behavior,
)
from app.contracts.messages.llm_request_context import (
    LLMRequestContext,
    build_agent_system_prompt,
)
from app.contracts.ports.agent_inference_context import (
    AgentInferenceContextError,
    AgentInferenceContextRequest,
    IAgentInferenceContextService,
)
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.relationship import IRelationshipQuery
from app.contracts.ports.tool_catalog import IToolCatalog

logger = logging.getLogger(__name__)


class AgentInferenceContextService(IAgentInferenceContextService):
    """Gather memory, profile, tool state, and available tool definitions."""

    def __init__(
        self,
        memory_service: IMemoryService,
        agent_profile_service: IAgentProfileService,
        tool_catalog: IToolCatalog,
        relationship_query: IRelationshipQuery,
    ) -> None:
        self._memory_service = memory_service
        self._agent_profile_service = agent_profile_service
        self._tool_catalog = tool_catalog
        self._relationship_query = relationship_query

    async def assemble(
        self,
        request: AgentInferenceContextRequest,
    ) -> Result[LLMRequestContext, AgentInferenceContextError]:
        memory_result = await self._memory_service.build_context(request.user_id)
        if is_err(memory_result):
            return Err(AgentInferenceContextError("Failed to retrieve memory context"))

        profile_bundle = self._agent_profile_service.load_agent_profile_bundle()
        relationship_result = await self._relationship_query.get(
            character_id=request.character_id,
            user_id=request.user_id,
        )
        if is_err(relationship_result):
            return Err(
                AgentInferenceContextError("Failed to retrieve relationship state")
            )
        directive = select_relationship_behavior(
            definition=profile_bundle.relationship,
            state=relationship_result.value,
            message_id=request.message_id,
        )
        allowed_tool_names = {"memory.read", "web_search"}
        tool_definitions = [
            definition
            for definition in self._tool_catalog.list_tools()
            if definition.name in allowed_tool_names
        ]

        return Ok(
            LLMRequestContext(
                system_prompt=build_agent_system_prompt(
                    "\n\n".join(
                        (
                            profile_bundle.persona_context,
                            render_relationship_behavior(directive),
                        )
                    ),
                    request.turn_context.conversation,
                ),
                tool_definitions=tool_definitions,
                memory_context=memory_result.value.assembled_context,
                recent_history=request.turn_context.recent_history,
                prompt=request.turn_context.prompt,
                tool_results=list(request.tool_results),
            )
        )
