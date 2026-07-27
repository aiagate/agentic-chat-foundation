"""Tests for channel-independent AI conversation generation."""

from datetime import UTC, datetime
from typing import Any

import pytest
from flow_res import Err, Ok

from app.application.conversation import (
    AIConversationResponseGenerator,
    ConversationGenerationContext,
)
from app.contracts.messages.agent_turn_context import AgentTurnContext
from app.contracts.messages.ai_continuation import AIContinuation
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.conversation import AcceptedMessage
from app.contracts.messages.conversation_context import ConversationContext
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.llm_request_context import LLMRequestContext
from app.contracts.messages.tool_contracts import (
    ToolCall,
    ToolDefinition,
    ToolExecutionResult,
)
from app.contracts.ports.agent_inference_context import IAgentInferenceContextService
from app.contracts.ports.ai_service import AIServiceError, IAIService
from app.contracts.ports.tool_executor import IToolExecutor


def _message() -> AcceptedMessage:
    return AcceptedMessage(
        message_id="message-1",
        character_id="character-1",
        user_id="user-1",
        external_conversation_id="line-conversation-1",
        external_participant_id="line-user-1",
        text="調べて",
        channel="LINE",
        occurred_at=datetime(2026, 7, 22, tzinfo=UTC),
    )


def _generation_context() -> ConversationGenerationContext:
    turn_context = AgentTurnContext(
        prompt="調べて",
        recent_history=[],
        conversation=ConversationContext(
            chat_scope="LINE user_id=user-1",
            current_time=datetime(2026, 7, 22, tzinfo=UTC),
            timezone="UTC",
            observed_message_count=1,
            has_session_boundary=False,
        ),
    )
    return ConversationGenerationContext(
        turn_context=turn_context,
        user_id="user-1",
        character_id="character-1",
        chat_type=ChatType.LINE,
        guild_id="DM",
        channel_id="line-conversation-1",
    )


def _llm_context() -> LLMRequestContext:
    return LLMRequestContext(
        prompt="調べて",
        tool_definitions=[
            ToolDefinition(
                name="web_search",
                description="Search the web.",
                arguments_schema={"type": "object"},
            )
        ],
    )


@pytest.mark.anyio
async def test_generator_passes_provider_continuation_after_tool_execution(
    mocker: Any,
) -> None:
    continuation = AIContinuation(provider="gemini", payload='{"role":"model"}')
    ai_service = mocker.Mock(spec=IAIService)
    ai_service.generate_content = mocker.AsyncMock(
        side_effect=[
            Ok(
                GeneratedContent(
                    tool_calls=[
                        ToolCall(
                            tool_call_id="call-1",
                            tool_name="web_search",
                            arguments={"query": "latest"},
                        )
                    ],
                    continuation=continuation,
                )
            ),
            Ok(GeneratedContent(contents=["調査結果です。"])),
        ]
    )
    inference_context = mocker.Mock(spec=IAgentInferenceContextService)
    inference_context.assemble = mocker.AsyncMock(return_value=Ok(_llm_context()))
    tool_executor = mocker.Mock(spec=IToolExecutor)
    tool_executor.execute = mocker.AsyncMock(
        return_value=Ok(
            ToolExecutionResult(
                tool_call_id="call-1",
                tool_name="web_search",
                status="ok",
                result={"result_count": 1},
                rendered_text="retrieved result",
            )
        )
    )
    generator = AIConversationResponseGenerator(
        ai_service,
        inference_context,
        tool_executor,
    )

    result = await generator.generate(_message(), _generation_context())

    assert result.contents == ("調査結果です。",)
    assert result.unavailable is False
    second_call = ai_service.generate_content.await_args_list[1]
    assert second_call.kwargs["continuation"] == continuation
    assert second_call.kwargs["tool_results"][0].tool_call_id == "call-1"


@pytest.mark.anyio
async def test_generator_hides_provider_error_from_channel_output(mocker: Any) -> None:
    ai_service = mocker.Mock(spec=IAIService)
    ai_service.generate_content = mocker.AsyncMock(
        return_value=Err(
            AIServiceError(
                "Gemini returned malformed internal output",
                code="gemini_invalid_response",
                retryable=False,
            )
        )
    )
    inference_context = mocker.Mock(spec=IAgentInferenceContextService)
    inference_context.assemble = mocker.AsyncMock(return_value=Ok(_llm_context()))
    tool_executor = mocker.Mock(spec=IToolExecutor)
    generator = AIConversationResponseGenerator(
        ai_service,
        inference_context,
        tool_executor,
    )

    result = await generator.generate(_message(), _generation_context())

    assert result.unavailable is True
    assert result.failure_reason == "応答を確定できませんでした。"
