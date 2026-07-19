"""Tests for prompt-ready agent inference context assembly."""

from datetime import UTC, datetime
from typing import Any

import pytest
from flow_res import Err, Ok, is_err

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.agent_turn_context import AgentTurnContext
from app.contracts.messages.character_definition import CharacterDefinition
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.conversation_context import ConversationContext
from app.contracts.messages.memory_context import MemoryContextPack
from app.contracts.messages.relationship import RelationshipStateView
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.agent_inference_context import AgentInferenceContextRequest
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.memory_service import IMemoryService, MemoryServiceError
from app.contracts.ports.relationship import IRelationshipQuery
from app.domain.aggregates.character_relationship import RelationshipStageId
from app.infrastructure.services.agent_inference_context import (
    AgentInferenceContextService,
)
from app.infrastructure.services.tool_catalog import StaticToolCatalog
from tests._relationship_fixture import relationship_definition


def _turn_context() -> AgentTurnContext:
    return AgentTurnContext(
        prompt="hello",
        recent_history=[],
        conversation=ConversationContext(
            chat_scope="LINE user_id=user-1",
            current_time=datetime(2026, 6, 29, tzinfo=UTC),
            timezone="UTC",
            observed_message_count=0,
            has_session_boundary=False,
        ),
    )


def _profile_bundle() -> AgentProfileBundle:
    return AgentProfileBundle(
        character=CharacterDefinition(character_id="character-1"),
        persona_context="Persona contract",
        relationship=relationship_definition(),
    )


def _service(mocker: Any, *, memory_result: Any) -> AgentInferenceContextService:
    memory_service = mocker.Mock(spec=IMemoryService)
    memory_service.build_context = mocker.AsyncMock(return_value=memory_result)
    profile_service = mocker.Mock(spec=IAgentProfileService)
    profile_service.load_agent_profile_bundle.return_value = _profile_bundle()
    relationship_query = mocker.Mock(spec=IRelationshipQuery)
    relationship_query.get = mocker.AsyncMock(
        return_value=Ok(
            RelationshipStateView(
                character_id="character-1",
                user_id="user-1",
                affection=0,
                stage_id=RelationshipStageId.DISTANT,
                version=1,
            )
        )
    )
    return AgentInferenceContextService(
        memory_service,
        profile_service,
        StaticToolCatalog(),
        relationship_query,
    )


@pytest.mark.anyio
async def test_context_service_assembles_line_tools_and_memory(mocker: Any) -> None:
    service = _service(
        mocker,
        memory_result=Ok(
            MemoryContextPack(user_id="user-1", assembled_context="Memory manifest")
        ),
    )

    result = await service.assemble(
        AgentInferenceContextRequest(
            turn_context=_turn_context(),
            message_id="message-1",
            user_id="user-1",
            character_id="character-1",
            chat_type=ChatType.LINE,
        )
    )

    assert not is_err(result)
    assert result.value.memory_context == "Memory manifest"
    assert "Persona contract" in (result.value.system_prompt or "")
    assert {tool.name for tool in result.value.tool_definitions} == {
        "web_search",
        "memory.read",
        "line.send",
    }


@pytest.mark.anyio
async def test_context_service_uses_durable_tool_results(mocker: Any) -> None:
    service = _service(
        mocker,
        memory_result=Ok(MemoryContextPack(user_id="user-1")),
    )

    result = await service.assemble(
        AgentInferenceContextRequest(
            turn_context=_turn_context(),
            message_id="message-1",
            user_id="user-1",
            character_id="character-1",
            chat_type=ChatType.LINE,
            tool_results=(
                ToolResultContext(
                    tool_call_id="tool-1",
                    character_id="character-1",
                    tool_name="web_search",
                    status="ok",
                    rendered_text="durable search result",
                ),
            ),
        )
    )

    assert not is_err(result)
    assert result.value.prompt == "hello"
    assert [item.rendered_text for item in result.value.tool_results] == [
        "durable search result"
    ]


@pytest.mark.anyio
async def test_context_service_maps_memory_failure(mocker: Any) -> None:
    service = _service(
        mocker,
        memory_result=Err(MemoryServiceError("memory failed")),
    )

    result = await service.assemble(
        AgentInferenceContextRequest(
            turn_context=_turn_context(),
            message_id="message-1",
            user_id="user-1",
            character_id="character-1",
            chat_type=ChatType.DISCORD,
        )
    )

    assert is_err(result)
    assert result.error.message == "Failed to retrieve memory context"
