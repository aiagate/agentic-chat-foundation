"""Generic tool executor for the agent runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.tool_contracts import (
    SearchToolArguments,
    ToolExecutionResult,
)
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.tool_executor import (
    IToolExecutor,
    ToolExecutionContext,
    ToolExecutorError,
)
from app.contracts.ports.web_search_service import IWebSearchService


class GenericToolExecutor(IToolExecutor):
    """Execute all application tools behind one adapter."""

    def __init__(
        self,
        *,
        memory_service: IMemoryService,
        web_search_service: IWebSearchService,
    ) -> None:
        self._memory_service = memory_service
        self._web_search_service = web_search_service

    async def execute(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        """Execute the requested tool and publish any side effects."""

        match context.tool_call.tool_name:
            case "web_search":
                result = await self._execute_web_search(context)
            case "memory.read":
                result = await self._execute_memory_read(context)
            case _:
                result = Err(
                    ToolExecutorError(
                        f"Unsupported tool: {context.tool_call.tool_name}"
                    )
                )

        return result

    async def _execute_web_search(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        arguments_result = _search_arguments(context.tool_call.arguments)
        if is_err(arguments_result):
            return Err(arguments_result.error)

        arguments = arguments_result.value
        tool_call_id = context.tool_call.tool_call_id or str(uuid4())
        search_result = await self._web_search_service.search(
            SearchToolArguments(
                query=arguments["query"],
                source_request_id=(arguments["source_request_id"] or context.chat_id),
                max_results=arguments["max_results"],
            )
        )
        if is_err(search_result):
            return Err(ToolExecutorError("Failed to execute web search"))

        search_results = search_result.value
        result = {
            "tool_call_id": tool_call_id,
            "retrieved_context": True,
            "result_count": len(search_results.items),
            "query": arguments["query"],
        }
        return Ok(
            _build_result(
                context,
                result,
                rendered_text=search_results.render_retrieved_context(tool_call_id),
            )
        )

    async def _execute_memory_read(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        memory_id = _require_nonempty_string(context.tool_call.arguments, "memory_id")
        if memory_id is None:
            return Err(ToolExecutorError("Tool call memory_id must not be empty"))

        retrieval_result = await self._memory_service.read_memory(
            memory_id,
            context.user_id,
        )
        if is_err(retrieval_result):
            return Err(ToolExecutorError("Failed to read memory"))

        memory_result = retrieval_result.value
        tool_call_id = context.tool_call.tool_call_id or str(uuid4())
        result = {
            "tool_call_id": tool_call_id,
            "retrieved_context": True,
            "result_count": 1,
            "memory_id": memory_id,
        }
        return Ok(
            _build_result(context, result, rendered_text=memory_result.rendered_text)
        )


def _build_result(
    context: ToolExecutionContext,
    result: Mapping[str, Any],
    *,
    rendered_text: str | None = None,
) -> ToolExecutionResult:
    return ToolExecutionResult(
        character_id=_context_character_id(context),
        tool_call_id=context.tool_call.tool_call_id,
        source_message_id=context.tool_call.source_message_id,
        decision_summary=context.tool_call.decision_summary,
        tool_name=context.tool_call.tool_name,
        status="ok",
        result=dict(result),
        rendered_text=rendered_text,
    )


def _search_arguments(arguments: dict[str, object]) -> Result[Any, ToolExecutorError]:
    query = _require_nonempty_string(arguments, "query")
    if query is None:
        return Err(ToolExecutorError("Tool call query must not be empty"))

    max_results = arguments.get("max_results")
    if max_results is not None:
        if not isinstance(max_results, int) or max_results <= 0:
            return Err(ToolExecutorError("Tool call max_results must be positive"))

    source_request_id = arguments.get("source_request_id")
    if source_request_id is not None and not isinstance(source_request_id, str):
        return Err(ToolExecutorError("Tool call source_request_id must be a string"))

    return Ok(
        {
            "query": query,
            "max_results": max_results,
            "source_request_id": source_request_id,
        }
    )


def _context_character_id(context: ToolExecutionContext) -> str:
    return context.character_id


def _require_nonempty_string(
    arguments: dict[str, object],
    key: str,
) -> str | None:
    value = arguments.get(key)
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return None
