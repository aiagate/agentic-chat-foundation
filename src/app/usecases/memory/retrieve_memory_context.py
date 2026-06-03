"""Retrieve memory context use case."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Ok, Result, is_err
from injector import inject

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.memory_context import MemoryContextPack
from app.contracts.ports.memory_service import IMemoryService
from app.usecases.result import ErrorType, UseCaseError


@dataclass(frozen=True)
class RetrieveMemoryContextQuery(Request[Result[MemoryContextPack, UseCaseError]]):
    """Query to resolve prompt-ready memory context."""

    history: Sequence[ChatHistoryItem]
    prompt: str
    user_id: str


class RetrieveMemoryContextHandler(
    RequestHandler[RetrieveMemoryContextQuery, Result[MemoryContextPack, UseCaseError]]
):
    """Handle RetrieveMemoryContextQuery."""

    @inject
    def __init__(self, memory_service: IMemoryService) -> None:
        self._memory_service = memory_service

    async def handle(
        self, request: RetrieveMemoryContextQuery
    ) -> Result[MemoryContextPack, UseCaseError]:
        """Resolve memory context through the memory port."""
        query = _build_memory_retrieval_query(
            request.history,
            request.prompt,
            max_messages=8,
        )
        memory_result = await self._memory_service.retrieve(
            query,
            request.user_id,
        )
        if is_err(memory_result):
            return memory_result.map_err(
                lambda _: UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message="Failed to retrieve memory context",
                )
            )
        return Ok(memory_result.value)


def _build_memory_retrieval_query(
    history: Sequence[ChatHistoryItem],
    prompt: str | None = None,
    *,
    max_messages: int = 8,
) -> str:
    """Build a retrieval query from the most recent chat messages."""

    if max_messages <= 0:
        raise ValueError("max_messages must be positive")

    history_texts = [text for text in (_chat_text(chat) for chat in history) if text]
    normalized_prompt = _normalize_text(prompt)
    if history_texts and normalized_prompt:
        if _normalize_text(history_texts[-1]) == normalized_prompt:
            selected = history_texts[-max_messages:]
        else:
            selected = history_texts[-max(max_messages - 1, 0) :]
            selected.append(normalized_prompt)
    elif normalized_prompt:
        selected = [normalized_prompt]
    else:
        selected = history_texts[-max_messages:]
    return "\n".join(line for line in selected if line)


def _chat_text(chat: ChatHistoryItem) -> str:
    return chat.content.strip()


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split())
