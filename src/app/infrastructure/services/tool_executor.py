"""Generic tool executor for the agent runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from flow_med import Mediator
from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.chat_events import (
    build_reply_ready_payload,
    reply_topic_for,
)
from app.contracts.messages.retrieved_context import (
    RetrievedContext,
    RetrievedContextItem,
)
from app.contracts.messages.tool_contracts import ToolExecutionResult
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_write_service import (
    IMemoryWriteService,
)
from app.contracts.ports.retrieved_context_store import (
    IRetrievedContextStore,
)
from app.contracts.ports.tool_executor import (
    IToolExecutor,
    ToolExecutionContext,
    ToolExecutorError,
)
from app.domain.value_objects.chat_type import ChatType
from app.usecases.search.run_web_search import (
    RunWebSearchCommand,
)


@dataclass(frozen=True)
class _NormalizedContents:
    contents: list[str]


class GenericToolExecutor(IToolExecutor):
    """Execute all application tools behind one adapter."""

    def __init__(
        self,
        *,
        event_bus: IEventBus,
        retrieved_context_store: IRetrievedContextStore,
        memory_service: IMemoryService,
        memory_write_service: IMemoryWriteService,
    ) -> None:
        self._event_bus = event_bus
        self._retrieved_context_store = retrieved_context_store
        self._memory_service = memory_service
        self._memory_write_service = memory_write_service

    async def execute(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        """Execute the requested tool and publish any side effects."""

        match context.tool_call.tool_name:
            case "web_search":
                return await self._execute_web_search(context)
            case "memory.search":
                return await self._execute_memory_search(context)
            case "memory.write_candidate":
                return await self._execute_memory_write_candidate(context)
            case "line.reply":
                return await self._execute_reply(context, ChatType.LINE)
            case "discord.reply":
                return await self._execute_reply(context, ChatType.DISCORD)
            case "discord.post_channel":
                return await self._execute_discord_post_channel(context)
            case _:
                return Err(
                    ToolExecutorError(
                        f"Unsupported tool: {context.tool_call.tool_name}"
                    )
                )

    async def _execute_web_search(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        arguments_result = _search_arguments(context.tool_call.arguments)
        if is_err(arguments_result):
            return Err(arguments_result.error)

        arguments = arguments_result.value
        tool_call_id = context.tool_call.tool_call_id or str(uuid4())
        run_result = await Mediator.send_async(
            RunWebSearchCommand(
                tool_call_id=tool_call_id,
                query=arguments["query"],
                user_message=context.tool_call.user_message,
                source_request_id=(arguments["source_request_id"] or context.chat_id),
                max_results=arguments["max_results"],
                tool_name="web_search",
                character_id=_context_character_id(context),
            )
        )
        if is_err(run_result):
            return Err(ToolExecutorError("Failed to execute web search"))

        result = {
            "tool_call_id": tool_call_id,
            "retrieved_context": True,
            "result_count": run_result.value.result_count,
            "query": arguments["query"],
        }
        return Ok(_build_result(context, result))

    async def _execute_memory_search(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        query = _require_nonempty_string(context.tool_call.arguments, "query")
        if query is None:
            return Err(ToolExecutorError("Tool call query must not be empty"))

        retrieval_result = await self._memory_service.retrieve(query, context.user_id)
        if is_err(retrieval_result):
            return Err(ToolExecutorError("Failed to execute memory search"))

        pack = retrieval_result.value
        tool_call_id = context.tool_call.tool_call_id or str(uuid4())
        items = _memory_items(pack)
        context_result = RetrievedContext(
            tool_call_id=tool_call_id,
            character_id=_context_character_id(context),
            query=query,
            tool_name="memory.search",
            items=items,
            rendered_text=pack.assembled_context or "",
        )
        save_result = await self._retrieved_context_store.save(context_result)
        if is_err(save_result):
            return Err(ToolExecutorError("Failed to store memory retrieved context"))

        result = {
            "tool_call_id": tool_call_id,
            "retrieved_context": True,
            "result_count": len(items),
            "query": query,
        }
        return Ok(_build_result(context, result))

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
        return Ok(_build_result(context, result))

    async def _execute_reply(
        self,
        context: ToolExecutionContext,
        chat_type: ChatType,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        if context.chat_type is not chat_type:
            return Err(
                ToolExecutorError(
                    f"{context.tool_call.tool_name} is not available for "
                    f"{context.chat_type.to_primitive()} chats"
                )
            )

        if chat_type is ChatType.DISCORD and not context.channel_id:
            return Err(ToolExecutorError("Discord reply requires a channel_id"))

        normalized = _normalize_contents(context.tool_call.arguments)
        if is_err(normalized):
            return Err(normalized.error)

        contents = normalized.value.contents
        if chat_type is ChatType.LINE:
            reply_payload = build_reply_ready_payload(
                chat_type=ChatType.LINE,
                contents=contents,
                user_id=context.user_id,
                agent_envelope=context.tool_call,
            )
            topic = reply_topic_for(ChatType.LINE)
        else:
            reply_payload = build_reply_ready_payload(
                chat_type=ChatType.DISCORD,
                contents=contents,
                guild_id=context.guild_id,
                channel_id=context.channel_id,
                agent_envelope=context.tool_call,
            )
            topic = reply_topic_for(ChatType.DISCORD)

        await self._event_bus.publish(topic, reply_payload)
        result = {
            "content_count": len(contents),
        }
        return Ok(_build_result(context, result))

    async def _execute_discord_post_channel(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        if context.chat_type is not ChatType.DISCORD:
            return Err(
                ToolExecutorError(
                    "discord.post_channel is only available for Discord chats"
                )
            )

        target_channel_id = _require_nonempty_string(
            context.tool_call.arguments,
            "target_channel_id",
        )
        if target_channel_id is None:
            return Err(
                ToolExecutorError("Tool call target_channel_id must not be empty")
            )

        normalized = _normalize_contents(context.tool_call.arguments)
        if is_err(normalized):
            return Err(normalized.error)

        contents = normalized.value.contents
        reply_payload = build_reply_ready_payload(
            chat_type=ChatType.DISCORD,
            contents=contents,
            guild_id=context.guild_id,
            channel_id=target_channel_id,
            agent_envelope=context.tool_call,
        )
        await self._event_bus.publish(reply_topic_for(ChatType.DISCORD), reply_payload)
        result = {
            "channel_id": target_channel_id,
            "content_count": len(contents),
        }
        return Ok(_build_result(context, result))


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


def _normalize_contents(
    arguments: dict[str, object],
) -> Result[_NormalizedContents, ToolExecutorError]:
    contents = arguments.get("contents")
    if isinstance(contents, list):
        normalized = [
            str(content).strip()
            for content in contents
            if isinstance(content, str) and content.strip()
        ]
        if normalized:
            return Ok(_NormalizedContents(contents=normalized))
        return Err(ToolExecutorError("Tool call contents must not be empty"))

    content = arguments.get("content")
    if isinstance(content, str) and content.strip():
        return Ok(_NormalizedContents(contents=[content.strip()]))

    return Err(ToolExecutorError("Tool call content must not be empty"))


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


def _memory_items(pack: Any) -> list[RetrievedContextItem]:
    items: list[RetrievedContextItem] = []
    search_hits = getattr(pack, "search_hits", [])
    if isinstance(search_hits, list) and search_hits:
        for hit in search_hits:
            source = getattr(hit, "source", None)
            items.append(
                RetrievedContextItem(
                    title=getattr(source, "title", None),
                    url=None,
                    snippet=getattr(hit, "excerpt", ""),
                    content=getattr(hit, "excerpt", None),
                    score=getattr(hit, "score", None),
                )
            )
        return items

    context_frame = getattr(pack, "context_frame", None)
    sections = getattr(context_frame, "sections", [])
    if isinstance(sections, list):
        for section in sections:
            items.append(
                RetrievedContextItem(
                    title=getattr(section, "name", None),
                    url=None,
                    snippet=getattr(section, "content", ""),
                    content=getattr(section, "content", None),
                    score=None,
                )
            )
    return items
