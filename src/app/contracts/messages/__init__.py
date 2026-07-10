"""Application messages and agentic trace DTOs."""

from app.contracts.messages.agent_profile import (
    AgentProfileBundle,
    render_agent_persona_context,
)
from app.contracts.messages.agent_turn_context import AgentTurnContext
from app.contracts.messages.agentic import (
    AgentEnvelope,
)
from app.contracts.messages.app_error import (
    APP_ERROR_DETECTED_TOPIC,
    AppErrorDetectedPayload,
    build_app_error_detected_payload,
)
from app.contracts.messages.character_definition import (
    CharacterDefinition,
    RelationshipDefaults,
)
from app.contracts.messages.chat_events import (
    CHAT_AGENT_TURN_REQUESTED_TOPIC,
    CHAT_TOOL_COMPLETED_TOPIC,
    CHAT_TOOL_REQUESTED_TOPIC,
    DISCORD_CHAT_REPLY_READY_TOPIC,
    DISCORD_CHAT_SAVED_TOPIC,
    LINE_CHAT_REPLY_READY_TOPIC,
    LINE_CHAT_SAVED_TOPIC,
    build_agent_turn_requested_payload,
    build_chat_tool_completed_payload,
    build_chat_tool_requested_payload,
    build_discord_chat_saved_payload,
    build_line_chat_saved_payload,
    build_reply_ready_payload,
    reply_topic_for,
)
from app.contracts.messages.chat_history import ChatHistoryItem, ChatHistoryWindow
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.conversation_context import (
    ConversationContext,
    render_conversation_context,
)
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.llm_request_context import (
    LLMCurrentInput,
    LLMRequestContext,
    build_agent_current_input,
    build_agent_system_prompt,
    compose_system_instruction,
)
from app.contracts.messages.memory_context import (
    MemoryContextPack,
    MemoryEntity,
    MemoryManifestItem,
    MemoryProfile,
    MemoryReadResult,
    MemoryTimelineEntry,
)
from app.contracts.messages.memory_index import (
    MemoryIndexDocument,
    MemoryIndexRecord,
    MemorySearchFilters,
    MemorySearchResult,
)
from app.contracts.messages.memory_semantic_extraction import (
    MemoryEntityPatch,
    MemoryEvidence,
    MemoryProfilePatch,
    MemorySemanticExtractionRequest,
    MemorySemanticExtractionResult,
    MemorySleepChatLog,
    MemoryTimelinePatch,
    MemoryTimelineSectionPatch,
)
from app.contracts.messages.outbox_message import OutboxMessage
from app.contracts.messages.relationship_growth import (
    MAX_DAILY_SCORE_INCREASE,
    RELATIONSHIP_ENTITY_TYPE,
    RELATIONSHIP_STAGES,
    RelationshipStage,
    clamp_relationship_score_increase,
    relationship_growth_stage_lines,
    resolve_relationship_stage,
)
from app.contracts.messages.tool_contracts import (
    SearchToolArguments,
    ToolArguments,
    ToolCall,
    ToolContinuation,
    ToolDefinition,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolSideEffect,
    normalize_reply_contents,
)
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.messages.web_search_result import (
    WebSearchResult,
    WebSearchResultItem,
)

__all__ = [
    "AgentEnvelope",
    "AgentTurnContext",
    "AgentProfileBundle",
    "ConversationContext",
    "CharacterDefinition",
    "ChatType",
    "RelationshipDefaults",
    "render_agent_persona_context",
    "render_conversation_context",
    "APP_ERROR_DETECTED_TOPIC",
    "AppErrorDetectedPayload",
    "ChatHistoryItem",
    "ChatHistoryWindow",
    "CHAT_TOOL_COMPLETED_TOPIC",
    "CHAT_AGENT_TURN_REQUESTED_TOPIC",
    "CHAT_TOOL_REQUESTED_TOPIC",
    "DISCORD_CHAT_REPLY_READY_TOPIC",
    "DISCORD_CHAT_SAVED_TOPIC",
    "GeneratedContent",
    "LLMCurrentInput",
    "LLMRequestContext",
    "LINE_CHAT_REPLY_READY_TOPIC",
    "LINE_CHAT_SAVED_TOPIC",
    "MemoryContextPack",
    "MemoryIndexDocument",
    "MemoryIndexRecord",
    "MemorySearchFilters",
    "MemorySearchResult",
    "MemoryEntity",
    "MemoryManifestItem",
    "MemoryEntityPatch",
    "MemoryEvidence",
    "MemoryProfile",
    "MemoryProfilePatch",
    "MemoryReadResult",
    "MemoryTimelineEntry",
    "MemorySemanticExtractionRequest",
    "MemorySemanticExtractionResult",
    "MemorySleepChatLog",
    "MemoryTimelineSectionPatch",
    "MemoryTimelinePatch",
    "OutboxMessage",
    "MAX_DAILY_SCORE_INCREASE",
    "RELATIONSHIP_ENTITY_TYPE",
    "RELATIONSHIP_STAGES",
    "RelationshipStage",
    "ToolArguments",
    "ToolCall",
    "ToolContinuation",
    "ToolDefinition",
    "ToolExecutionResult",
    "ToolExecutionStatus",
    "SearchToolArguments",
    "ToolSideEffect",
    "ToolResultContext",
    "WebSearchResultItem",
    "WebSearchResult",
    "build_app_error_detected_payload",
    "build_agent_turn_requested_payload",
    "build_agent_current_input",
    "build_agent_system_prompt",
    "build_chat_tool_completed_payload",
    "build_chat_tool_requested_payload",
    "build_discord_chat_saved_payload",
    "build_line_chat_saved_payload",
    "build_reply_ready_payload",
    "clamp_relationship_score_increase",
    "compose_system_instruction",
    "relationship_growth_stage_lines",
    "reply_topic_for",
    "normalize_reply_contents",
    "resolve_relationship_stage",
]
