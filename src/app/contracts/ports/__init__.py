"""Application ports."""

from app.contracts.ports.agent_inference_context import (
    AgentInferenceContextError,
    AgentInferenceContextRequest,
    IAgentInferenceContextService,
)
from app.contracts.ports.agent_turn_context_query import (
    AgentTurnContextQueryError,
    IAgentTurnContextQuery,
)
from app.contracts.ports.ai_service import AIServiceError, IAIService
from app.contracts.ports.conversation import (
    ConversationContext,
    ConversationHistory,
    ConversationResultSender,
    ResponseGenerator,
)
from app.contracts.ports.discussion import (
    IAgentTurnEvaluator,
    IAutonomousTopicEvaluator,
    IAutonomousTopicGuard,
    IAutonomousTopicRepository,
    IDiscussionMessageSender,
    IDiscussionRepository,
    ILocalSpeechGuard,
)
from app.contracts.ports.embedding_service import (
    EmbeddingServiceError,
    IEmbeddingService,
)
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_index_projection import (
    IMemoryIndexProjection,
    MemoryIndexError,
)
from app.contracts.ports.memory_index_query import (
    IMemoryIndexQuery,
    MemoryIndexQueryError,
)
from app.contracts.ports.memory_semantic_extraction import (
    IMemorySemanticExtractionService,
    MemorySemanticExtractionError,
)
from app.contracts.ports.memory_service import IMemoryService, MemoryServiceError
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.tool_catalog import IToolCatalog
from app.contracts.ports.tool_executor import (
    IToolExecutor,
    ToolExecutionContext,
    ToolExecutorError,
)
from app.contracts.ports.unit_of_work import IUnitOfWork, IUnitOfWorkFactory
from app.contracts.ports.user_identity_query import IUserIdentityQuery
from app.contracts.ports.web_search_service import (
    IWebSearchService,
    WebSearchServiceError,
)

__all__ = [
    "AIServiceError",
    "AgentInferenceContextError",
    "AgentInferenceContextRequest",
    "AgentTurnContextQueryError",
    "EmbeddingServiceError",
    "ConversationContext",
    "ConversationHistory",
    "ConversationResultSender",
    "ResponseGenerator",
    "IAIService",
    "IAgentInferenceContextService",
    "IAgentTurnContextQuery",
    "IEmbeddingService",
    "IAgentTurnEvaluator",
    "IAutonomousTopicEvaluator",
    "IAutonomousTopicGuard",
    "IAutonomousTopicRepository",
    "IDiscussionMessageSender",
    "IDiscussionRepository",
    "ILocalSpeechGuard",
    "IMemoryConsolidationService",
    "IMemoryIndexQuery",
    "IMemoryIndexProjection",
    "IMemoryService",
    "IMemorySemanticExtractionService",
    "IMemoryStore",
    "MemoryIndexQueryError",
    "MemoryIndexError",
    "MemoryServiceError",
    "MemorySemanticExtractionError",
    "IToolCatalog",
    "IToolExecutor",
    "ToolExecutionContext",
    "ToolExecutorError",
    "IUnitOfWork",
    "IUnitOfWorkFactory",
    "IUserIdentityQuery",
    "IWebSearchService",
    "WebSearchServiceError",
]
