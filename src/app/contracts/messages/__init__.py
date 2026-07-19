"""Application messages and agentic trace DTOs."""

from app.contracts.messages.agent_profile import (
    AgentProfileBundle,
    render_agent_persona_context,
)
from app.contracts.messages.agent_turn_context import AgentTurnContext
from app.contracts.messages.agentic import (
    AgentEnvelope,
)
from app.contracts.messages.character_definition import (
    CharacterDefinition,
)
from app.contracts.messages.chat_history import ChatHistoryItem, ChatHistoryWindow
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.conversation import (
    AcceptedMessage,
    ConversationResult,
    DeliveryResult,
    IncomingMessage,
)
from app.contracts.messages.conversation_context import (
    ConversationContext,
    render_conversation_context,
)
from app.contracts.messages.discussion import (
    AgentTurnDecision,
    AgentTurnDisposition,
    AgentTurnRecord,
    AutonomousTopicActivity,
    AutonomousTopicContext,
    AutonomousTopicTurnRecord,
    DiscussionActivity,
    DiscussionAuthorKind,
    DiscussionContextMessage,
    DiscussionHistoryItem,
    DiscussionParticipantContext,
    DiscussionTurnContext,
    IncomingDiscussionMessage,
    ObservedDiscussionMessage,
    PrivateReflection,
    SentDiscussionMessage,
    TopicStimulus,
)
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.llm_request_context import (
    LLMRequestContext,
    build_agent_system_prompt,
    compose_system_instruction,
    render_agent_prompt,
)
from app.contracts.messages.memory_consolidation import (
    MemoryChangeSet,
    MemoryConsolidationResult,
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
    LongTermMemoryChatLog,
    MemoryEntityPatch,
    MemoryEvidence,
    MemoryProfilePatch,
    MemorySemanticExtractionRequest,
    MemorySemanticExtractionResult,
    MemoryTimelineSectionPatch,
)
from app.contracts.messages.relationship import (
    CharacterRelationshipDefinition,
    RelationshipBehaviorDirective,
    RelationshipSignalCandidate,
    RelationshipSignalKind,
    RelationshipStateView,
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
    "AgentTurnDecision",
    "AgentTurnDisposition",
    "AgentTurnRecord",
    "AutonomousTopicActivity",
    "AutonomousTopicContext",
    "AutonomousTopicTurnRecord",
    "AgentTurnContext",
    "AgentProfileBundle",
    "ConversationContext",
    "CharacterDefinition",
    "ChatType",
    "AcceptedMessage",
    "ConversationResult",
    "DeliveryResult",
    "DiscussionActivity",
    "DiscussionAuthorKind",
    "DiscussionContextMessage",
    "DiscussionHistoryItem",
    "DiscussionParticipantContext",
    "DiscussionTurnContext",
    "IncomingMessage",
    "IncomingDiscussionMessage",
    "ObservedDiscussionMessage",
    "PrivateReflection",
    "CharacterRelationshipDefinition",
    "RelationshipBehaviorDirective",
    "RelationshipSignalCandidate",
    "RelationshipSignalKind",
    "RelationshipStateView",
    "render_agent_persona_context",
    "render_conversation_context",
    "ChatHistoryItem",
    "ChatHistoryWindow",
    "GeneratedContent",
    "LLMRequestContext",
    "MemoryContextPack",
    "MemoryChangeSet",
    "MemoryConsolidationResult",
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
    "LongTermMemoryChatLog",
    "MemoryTimelineSectionPatch",
    "ToolArguments",
    "ToolCall",
    "ToolContinuation",
    "ToolDefinition",
    "ToolExecutionResult",
    "ToolExecutionStatus",
    "SearchToolArguments",
    "SentDiscussionMessage",
    "TopicStimulus",
    "ToolSideEffect",
    "ToolResultContext",
    "WebSearchResultItem",
    "WebSearchResult",
    "build_agent_system_prompt",
    "compose_system_instruction",
    "render_agent_prompt",
    "normalize_reply_contents",
]
