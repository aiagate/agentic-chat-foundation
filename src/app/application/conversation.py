"""Application services supporting the channel-independent response flow."""

from dataclasses import dataclass

from flow_res import is_err

from app.contracts.messages.agent_turn_context import AgentTurnContext
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.conversation import (
    AcceptedMessage,
    ConversationResult,
)
from app.contracts.messages.llm_request_context import compose_system_instruction
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.agent_inference_context import (
    AgentInferenceContextRequest,
    IAgentInferenceContextService,
)
from app.contracts.ports.agent_turn_context_query import IAgentTurnContextQuery
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.conversation import (
    ConversationContext,
    ResponseGenerator,
)
from app.contracts.ports.tool_executor import IToolExecutor, ToolExecutionContext


@dataclass(frozen=True, slots=True)
class ConversationGenerationContext:
    """Prompt-ready context and identity for one accepted message."""

    turn_context: AgentTurnContext
    user_id: str
    character_id: str
    chat_type: ChatType
    guild_id: str
    channel_id: str


class SQLAlchemyConversationContext(ConversationContext):
    """Load recent history and conversation metadata for response generation."""

    def __init__(
        self,
        query: IAgentTurnContextQuery,
        character_id: str,
    ) -> None:
        self._query = query
        self._character_id = character_id

    async def load(self, message: AcceptedMessage) -> ConversationGenerationContext:
        chat_type = ChatType.from_primitive(message.channel).unwrap()
        guild_id = message.metadata.get("guild_id", "DM")
        channel_id = message.metadata.get(
            "channel_id", message.conversation_id
        )
        result = await self._query.load(
            chat_id=message.message_id,
            provided_prompt=message.text,
            chat_type=chat_type,
            user_id=message.participant_id,
            guild_id=guild_id,
            channel_id=channel_id,
        )
        if is_err(result):
            raise RuntimeError(result.error.message)
        return ConversationGenerationContext(
            turn_context=result.value,
            user_id=message.participant_id,
            character_id=self._character_id,
            chat_type=chat_type,
            guild_id=guild_id,
            channel_id=channel_id,
        )


class AIConversationResponseGenerator(ResponseGenerator):
    """Create one response without durable run, retry, or recovery state."""

    def __init__(
        self,
        ai_service: IAIService,
        inference_context: IAgentInferenceContextService,
        tool_executor: IToolExecutor,
    ) -> None:
        self._ai_service = ai_service
        self._inference_context = inference_context
        self._tool_executor = tool_executor

    async def generate(
        self,
        message: AcceptedMessage,
        context: object,
    ) -> ConversationResult:
        if not isinstance(context, ConversationGenerationContext):
            raise TypeError("Unexpected conversation context")
        tool_results: list[ToolResultContext] = []
        assembled = await self._inference_context.assemble(
            AgentInferenceContextRequest(
                turn_context=context.turn_context,
                user_id=context.user_id,
                character_id=context.character_id,
                chat_type=context.chat_type,
                tool_results=tuple(tool_results),
            )
        )
        if is_err(assembled):
            return ConversationResult(
                message_id=message.message_id,
                conversation_id=message.conversation_id,
                channel=message.channel,
                unavailable=True,
                failure_reason=assembled.error.message,
            )
        generated = await self._ai_service.generate_content(
            assembled.value.prompt,
            assembled.value.recent_history,
            system_instruction=compose_system_instruction(assembled.value),
            tool_definitions=assembled.value.tool_definitions,
            tool_results=list(tool_results),
        )
        if is_err(generated):
            return ConversationResult(
                message_id=message.message_id,
                conversation_id=message.conversation_id,
                channel=message.channel,
                unavailable=True,
                failure_reason=generated.error.message,
            )
        for tool_call in generated.value.tool_calls[:3]:
            execution = await self._tool_executor.execute(
                ToolExecutionContext(
                    chat_id=message.message_id,
                    user_id=context.user_id,
                    chat_type=context.chat_type,
                    tool_call=tool_call,
                    character_id=context.character_id,
                    guild_id=context.guild_id,
                    channel_id=context.channel_id,
                )
            )
            if is_err(execution):
                return ConversationResult(
                    message_id=message.message_id,
                    conversation_id=message.conversation_id,
                    channel=message.channel,
                    unavailable=True,
                    failure_reason=execution.error.message,
                )
            tool_result = execution.value
            tool_results.append(
                ToolResultContext(
                    tool_call_id=tool_call.tool_call_id or tool_call.tool_name,
                    character_id=context.character_id,
                    tool_name=tool_result.tool_name,
                    status=tool_result.status,
                    result=dict(tool_result.result),
                    error=tool_result.error,
                    rendered_text=tool_result.rendered_text or str(tool_result.result),
                )
            )
        if generated.value.tool_calls:
            assembled = await self._inference_context.assemble(
                AgentInferenceContextRequest(
                    turn_context=context.turn_context,
                    user_id=context.user_id,
                    character_id=context.character_id,
                    chat_type=context.chat_type,
                    tool_results=tuple(tool_results),
                )
            )
            if is_err(assembled):
                return ConversationResult(
                    message_id=message.message_id,
                    conversation_id=message.conversation_id,
                    channel=message.channel,
                    unavailable=True,
                    failure_reason=assembled.error.message,
                )
            generated = await self._ai_service.generate_content(
                assembled.value.prompt,
                assembled.value.recent_history,
                system_instruction=compose_system_instruction(assembled.value),
                tool_definitions=assembled.value.tool_definitions,
                tool_results=list(tool_results),
            )
            if is_err(generated) or generated.value.tool_calls:
                return ConversationResult(
                    message_id=message.message_id,
                    conversation_id=message.conversation_id,
                    channel=message.channel,
                    unavailable=True,
                    failure_reason="応答を確定できませんでした。",
                )
        return ConversationResult(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            channel=message.channel,
            contents=tuple(generated.value.contents),
        )
