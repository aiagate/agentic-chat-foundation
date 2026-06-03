"""Application messages and agentic trace DTOs."""

from app.contracts.messages.agent_profile import (
    AgentProfileBundle,
    render_agent_persona_context,
)
from app.contracts.messages.agentic import (
    AgentEnvelope,
)
from app.contracts.messages.app_error import (
    APP_ERROR_DETECTED_TOPIC,
    AppErrorDetectedPayload,
    build_app_error_detected_payload,
)
from app.contracts.messages.character_definition import (
    ACTIVE_CHARACTER_ID_ENV_VAR,
    BUILTIN_CHARACTER_DEFINITIONS,
    DEFAULT_CHARACTER_ID,
    CharacterDefinition,
    RelationshipDefaults,
    resolve_character_definition,
    selected_character_definition,
    selected_character_id,
)
from app.contracts.messages.chat_events import (
    CHAT_TOOL_COMPLETED_TOPIC,
    CHAT_TOOL_REQUESTED_TOPIC,
    DISCORD_CHAT_REPLY_READY_TOPIC,
    DISCORD_CHAT_SAVED_TOPIC,
    LINE_CHAT_REPLY_READY_TOPIC,
    LINE_CHAT_SAVED_TOPIC,
    build_chat_tool_completed_payload,
    build_chat_tool_requested_payload,
    build_discord_chat_saved_payload,
    build_line_chat_saved_payload,
    build_reply_ready_payload,
    reply_topic_for,
)
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.conversation_context import (
    ConversationContext,
    render_conversation_context,
)
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.memory_context import (
    MemoryContextPack,
    MemoryEntity,
    MemoryProfile,
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
from app.contracts.messages.relationship_growth import (
    MAX_DAILY_SCORE_INCREASE,
    RELATIONSHIP_ENTITY_TYPE,
    RELATIONSHIP_STAGES,
    RelationshipStage,
    clamp_relationship_score_increase,
    relationship_growth_stage_lines,
    resolve_relationship_stage,
)
from app.contracts.messages.retrieved_context import (
    RetrievedContext,
    RetrievedContextItem,
)
from app.contracts.messages.tool_contracts import (
    SearchToolArguments,
    ToolArguments,
    ToolCall,
    ToolDefinition,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolName,
    ToolSideEffect,
)

__all__ = [
    "AgentEnvelope",
    "AgentProfileBundle",
    "ACTIVE_CHARACTER_ID_ENV_VAR",
    "BUILTIN_CHARACTER_DEFINITIONS",
    "ConversationContext",
    "CharacterDefinition",
    "DEFAULT_CHARACTER_ID",
    "RelationshipDefaults",
    "render_agent_persona_context",
    "render_conversation_context",
    "APP_ERROR_DETECTED_TOPIC",
    "AppErrorDetectedPayload",
    "ChatHistoryItem",
    "CHAT_TOOL_COMPLETED_TOPIC",
    "CHAT_TOOL_REQUESTED_TOPIC",
    "DISCORD_CHAT_REPLY_READY_TOPIC",
    "DISCORD_CHAT_SAVED_TOPIC",
    "GeneratedContent",
    "LINE_CHAT_REPLY_READY_TOPIC",
    "LINE_CHAT_SAVED_TOPIC",
    "MemoryContextPack",
    "MemoryIndexDocument",
    "MemoryIndexRecord",
    "MemorySearchFilters",
    "MemorySearchResult",
    "MemoryEntity",
    "MemoryEntityPatch",
    "MemoryEvidence",
    "MemoryProfile",
    "MemoryProfilePatch",
    "MemoryTimelineEntry",
    "MemorySemanticExtractionRequest",
    "MemorySemanticExtractionResult",
    "MemorySleepChatLog",
    "MemoryTimelineSectionPatch",
    "MemoryTimelinePatch",
    "MAX_DAILY_SCORE_INCREASE",
    "RELATIONSHIP_ENTITY_TYPE",
    "RELATIONSHIP_STAGES",
    "RelationshipStage",
    "RetrievedContext",
    "RetrievedContextItem",
    "ToolArguments",
    "ToolCall",
    "ToolDefinition",
    "ToolExecutionResult",
    "ToolExecutionStatus",
    "SearchToolArguments",
    "ToolSideEffect",
    "ToolName",
    "build_app_error_detected_payload",
    "build_chat_tool_completed_payload",
    "build_chat_tool_requested_payload",
    "build_discord_chat_saved_payload",
    "build_line_chat_saved_payload",
    "build_reply_ready_payload",
    "clamp_relationship_score_increase",
    "relationship_growth_stage_lines",
    "reply_topic_for",
    "resolve_relationship_stage",
    "resolve_character_definition",
    "selected_character_definition",
    "selected_character_id",
]
