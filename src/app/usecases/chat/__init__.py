"""Chat use cases."""

from app.usecases.chat.generate_content import (
    GenerateContentHandler,
    GenerateContentQuery,
    GenerateContentResult,
)
from app.usecases.chat.generate_content_with_retrieved_context import (
    GenerateContentWithRetrievedContextHandler,
    GenerateContentWithRetrievedContextQuery,
    GenerateContentWithRetrievedContextResult,
)
from app.usecases.chat.save_chat import (
    SaveChatHandler,
    SaveChatResult,
    SaveDiscordChatCommand,
)
from app.usecases.chat.save_line_chat import SaveLineChatCommand

__all__ = [
    "GenerateContentHandler",
    "GenerateContentQuery",
    "GenerateContentResult",
    "GenerateContentWithRetrievedContextHandler",
    "GenerateContentWithRetrievedContextQuery",
    "GenerateContentWithRetrievedContextResult",
    "SaveDiscordChatCommand",
    "SaveChatHandler",
    "SaveChatResult",
    "SaveLineChatCommand",
]
