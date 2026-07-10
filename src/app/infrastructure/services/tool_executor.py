"""Generic tool executor for the agent runtime."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.tool_contracts import (
    SearchToolArguments,
    ToolExecutionResult,
    normalize_reply_contents,
)
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.agent_reply_writer import (
    AgentReplyWriteRequest,
    IAgentReplyWriter,
)
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_write_service import (
    IMemoryWriteService,
)
from app.contracts.ports.tool_executor import (
    IToolExecutor,
    ToolExecutionContext,
    ToolExecutorError,
)
from app.contracts.ports.tool_result_store import IToolResultStore
from app.contracts.ports.web_search_service import IWebSearchService
from app.domain.value_objects.chat_type import ChatType


class GenericToolExecutor(IToolExecutor):
    """Execute all application tools behind one adapter."""

    def __init__(
        self,
        *,
        tool_result_store: IToolResultStore,
        memory_service: IMemoryService,
        memory_write_service: IMemoryWriteService,
        web_search_service: IWebSearchService,
        agent_reply_writer: IAgentReplyWriter,
    ) -> None:
        self._tool_result_store = tool_result_store
        self._memory_service = memory_service
        self._memory_write_service = memory_write_service
        self._web_search_service = web_search_service
        self._agent_reply_writer = agent_reply_writer

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
            case "memory.write_candidate":
                result = await self._execute_memory_write_candidate(context)
            case "line.send" | "discord.send":
                result = await self._execute_send_message(context)
            case _:
                result = Err(
                    ToolExecutorError(
                        f"Unsupported tool: {context.tool_call.tool_name}"
                    )
                )

        if is_err(result) and context.tool_call.tool_name not in {
            "line.send",
            "discord.send",
        }:
            await self._store_failure(context, result.error.message)
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
        return await self._store_success(
            context,
            result,
            rendered_text=search_results.render_retrieved_context(tool_call_id),
        )

    async def _execute_send_message(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        contents = normalize_reply_contents(context.tool_call.arguments)
        if contents is None:
            return Err(ToolExecutorError("Tool call content must not be empty"))

        guild_id = context.guild_id or "DM"
        channel_id = context.channel_id or ""
        if context.tool_call.tool_name == "line.send":
            if context.chat_type is not ChatType.LINE:
                return Err(
                    ToolExecutorError("line.send is only available for LINE chats")
                )
            guild_id = "LINE"
            channel_id = context.user_id
        elif context.chat_type is not ChatType.DISCORD:
            return Err(
                ToolExecutorError("discord.send is only available for Discord chats")
            )
        elif not context.channel_id:
            return Err(ToolExecutorError("Discord send requires a channel_id"))

        reply_result = await self._agent_reply_writer.write(
            AgentReplyWriteRequest(
                chat_type=context.chat_type,
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=context.user_id,
                contents=contents,
                agent_context=context.tool_call,
            )
        )
        if is_err(reply_result):
            return Err(ToolExecutorError(reply_result.error.message))
        return Ok(_build_result(context, {"content_count": len(contents)}))

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
        return await self._store_success(
            context,
            result,
            rendered_text=memory_result.rendered_text,
        )

    async def _execute_memory_write_candidate(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        content = _require_nonempty_string(context.tool_call.arguments, "content")
        if content is None:
            return Err(ToolExecutorError("Tool call content must not be empty"))

        role = _normalized_role(context.tool_call.arguments.get("role"))
        metadata = _normalized_metadata(context)
        metadata_payload = dict(metadata)
        write_result = await self._memory_write_service.add_log(
            user_id=context.user_id,
            role=role,
            content=content,
            metadata=metadata_payload,
        )
        if is_err(write_result):
            return Err(ToolExecutorError("Failed to write memory candidate"))

        result = {
            "written": True,
            "role": role,
            "content_length": len(content),
        }
        return await self._store_success(
            context,
            result,
            rendered_text=json.dumps(result, ensure_ascii=False),
        )

    async def _store_success(
        self,
        context: ToolExecutionContext,
        result: Mapping[str, object],
        *,
        rendered_text: str,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        tool_call_id = context.tool_call.tool_call_id
        if tool_call_id is None:
            return Err(ToolExecutorError("Tool call ID is required"))
        save_result = await self._tool_result_store.save(
            ToolResultContext(
                tool_call_id=tool_call_id,
                character_id=_context_character_id(context),
                tool_name=context.tool_call.tool_name,
                status="ok",
                result=dict(result),
                rendered_text=rendered_text,
            )
        )
        if is_err(save_result):
            return Err(ToolExecutorError("Failed to store tool result"))
        return Ok(_build_result(context, result))

    async def _store_failure(
        self,
        context: ToolExecutionContext,
        error: str,
    ) -> None:
        tool_call_id = context.tool_call.tool_call_id
        if tool_call_id is None:
            return
        await self._tool_result_store.save(
            ToolResultContext(
                tool_call_id=tool_call_id,
                character_id=_context_character_id(context),
                tool_name=context.tool_call.tool_name,
                status="error",
                error=error,
                rendered_text=f"{context.tool_call.tool_name} failed: {error}",
            )
        )


def _build_result(
    context: ToolExecutionContext,
    result: Mapping[str, Any],
) -> ToolExecutionResult:
    return ToolExecutionResult(
        event_id=context.tool_call.event_id,
        correlation_id=context.tool_call.correlation_id,
        causation_id=context.tool_call.causation_id,
        agent_run_id=context.tool_call.agent_run_id,
        agent_turn_id=context.tool_call.agent_turn_id,
        character_id=_context_character_id(context),
        tool_call_id=context.tool_call.tool_call_id,
        source_message_id=context.tool_call.source_message_id,
        decision_summary=context.tool_call.decision_summary,
        tool_name=context.tool_call.tool_name,
        status="ok",
        result=dict(result),
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


def _normalized_role(value: object) -> str:
    if isinstance(value, str) and value.strip():
        role = value.strip()
        if role in {"user", "assistant", "system"}:
            return role
    return "assistant"


def _normalized_metadata(context: ToolExecutionContext) -> dict[str, str]:
    metadata: dict[str, str] = {
        "chat_id": context.chat_id,
        "chat_type": context.chat_type.to_primitive(),
        "tool_name": context.tool_call.tool_name,
    }
    if context.guild_id is not None:
        metadata["guild_id"] = context.guild_id
    if context.channel_id is not None:
        metadata["channel_id"] = context.channel_id
    if context.tool_call.tool_call_id is not None:
        metadata["tool_call_id"] = context.tool_call.tool_call_id
    if context.tool_call.agent_run_id is not None:
        metadata["agent_run_id"] = context.tool_call.agent_run_id
    if context.tool_call.agent_turn_id is not None:
        metadata["agent_turn_id"] = context.tool_call.agent_turn_id
    if context.tool_call.decision_summary is not None:
        metadata["decision_summary"] = context.tool_call.decision_summary

    raw_metadata = context.tool_call.arguments.get("metadata")
    if isinstance(raw_metadata, dict):
        for key, value in raw_metadata.items():
            if value is None:
                continue
            metadata[str(key)] = str(value)
    return metadata
