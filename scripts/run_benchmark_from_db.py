"""Run a small benchmark from database chat history and render a report."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, cast

from dotenv import load_dotenv
from flow_res import Ok, Result, is_err
from google import genai
from google.genai import types
from openai import AsyncOpenAI
from openai.types.responses import ResponseInputItemParam
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.character_selection import resolve_active_character_id
from app.contracts.messages.agent_turn_context import AgentTurnContext
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.conversation_context import ConversationContext
from app.contracts.messages.llm_request_context import compose_system_instruction
from app.contracts.messages.memory_index import MemoryIndexDocument
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.ports.agent_inference_context import AgentInferenceContextRequest
from app.contracts.ports.memory_index_query import (
    IMemoryIndexQuery,
    MemoryIndexQueryError,
)
from app.domain.value_objects.message_content import render_message_content_text
from app.infrastructure import database
from app.infrastructure.benchmark.report import (
    BenchmarkRecord,
    write_benchmark_reports,
)
from app.infrastructure.memory.store import FilesystemMemoryStore, default_memory_root
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.infrastructure.queries.agent_turn_context_query import latest_session_window
from app.infrastructure.queries.memory_index_projection_query import (
    SQLAlchemyMemoryIndexQuery,
)
from app.infrastructure.serializers.provider_tool_binding import (
    bind_provider_tools,
)
from app.infrastructure.services.agent_inference_context import (
    AgentInferenceContextService,
)
from app.infrastructure.services.agent_profile_service import (
    FilesystemAgentProfileService,
)
from app.infrastructure.services.gemini_service import _gemini_tools
from app.infrastructure.services.gpt_service import _openai_tools
from app.infrastructure.services.memory_service import FilesystemMemoryService
from app.infrastructure.services.tool_catalog import StaticToolCatalog

_OPENAI_MODELS = (
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
)
_GEMINI_MODELS = (
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite",
)
_DEFAULT_OPENAI_MAX_OUTPUT_TOKENS = 1024
_DEFAULT_GEMINI_MAX_OUTPUT_TOKENS = 2048
_GEMINI_RETRY_ATTEMPTS = 3
_GEMINI_RETRY_DELAY_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class BenchmarkStyleProfile:
    """Prompt and provider-specific generation settings for one benchmark."""

    name: str
    system_prompt_suffix: str
    openai_reasoning_effort: str | None
    openai_text_verbosity: str | None
    gemini_pro_thinking_level: types.ThinkingLevel
    gemini_flash_thinking_level: types.ThinkingLevel
    gemini_temperature: float | None


_HUMAN_SNS_SYSTEM_SUFFIX = (
    "SNS reply style for this benchmark:\n"
    "- Write one natural LINE/DM reply, 2 to 4 sentences, roughly "
    "120 to 260 Japanese characters.\n"
    "- Do not use headings, bullet points, numbered lists, Markdown, "
    "or a formal closing.\n"
    "- First acknowledge one specific feeling from the user's words, "
    "then offer at most one small practical next step or question.\n"
    "- Prefer one ordinary action for tonight or tomorrow. Do not propose "
    "symptom logs, self-assessment, monitoring plans, or a consultation plan "
    "unless the message clearly requires it.\n"
    "- Avoid generic praise, diagnosis, excessive reassurance, and "
    "lecturing. Use everyday Japanese; avoid clinical or business terms such "
    "as '見える化' or 'キャパシティ'. Do not repeat the user's full "
    "situation.\n"
    "- Treat ordinary low mood as a conversational concern; do not add "
    "a routine medical-provider or helpline recommendation. If the "
    "message contains clear imminent danger, prioritize brief safety "
    "guidance instead.\n"
    "- Return only the reply text."
)


_STYLE_PROFILES: dict[str, BenchmarkStyleProfile] = {
    "application": BenchmarkStyleProfile(
        name="application",
        system_prompt_suffix="",
        openai_reasoning_effort=None,
        openai_text_verbosity=None,
        gemini_pro_thinking_level=types.ThinkingLevel.LOW,
        gemini_flash_thinking_level=types.ThinkingLevel.LOW,
        gemini_temperature=None,
    ),
    "human-sns": BenchmarkStyleProfile(
        name="human-sns",
        system_prompt_suffix=_HUMAN_SNS_SYSTEM_SUFFIX,
        openai_reasoning_effort="none",
        openai_text_verbosity="low",
        gemini_pro_thinking_level=types.ThinkingLevel.LOW,
        gemini_flash_thinking_level=types.ThinkingLevel.MINIMAL,
        gemini_temperature=None,
    ),
    "human-sns-reasoned": BenchmarkStyleProfile(
        name="human-sns-reasoned",
        system_prompt_suffix=_HUMAN_SNS_SYSTEM_SUFFIX,
        openai_reasoning_effort="low",
        openai_text_verbosity="low",
        gemini_pro_thinking_level=types.ThinkingLevel.LOW,
        gemini_flash_thinking_level=types.ThinkingLevel.LOW,
        gemini_temperature=None,
    ),
}


@dataclass(frozen=True, slots=True)
class BenchmarkContext:
    """The immutable prompt context shared by every model call."""

    system_prompt: str
    history: tuple[ChatHistoryItem, ...]
    prompt: str
    tool_definitions: tuple[ToolDefinition, ...] = ()


@dataclass(slots=True)
class _BenchmarkMemoryIndexQuery(IMemoryIndexQuery):
    """Expose only memory that existed before the benchmark target turn."""

    delegate: IMemoryIndexQuery
    cutoff: datetime
    excluded_chat_ids: frozenset[str]
    prompt: str

    async def list_documents(
        self,
        *,
        user_id: str,
        character_id: str,
        relationship_entity_id: str,
    ) -> Result[list[MemoryIndexDocument], MemoryIndexQueryError]:
        result = await self.delegate.list_documents(
            user_id=user_id,
            character_id=character_id,
            relationship_entity_id=relationship_entity_id,
        )
        if is_err(result):
            return result
        return Ok(
            [
                document
                for document in result.value
                if _memory_document_is_available(document, self)
            ]
        )


def _memory_document_is_available(
    document: MemoryIndexDocument,
    context: _BenchmarkMemoryIndexQuery,
) -> bool:
    front_matter = document.document.front_matter
    source_chat_ids = {
        str(value)
        for key in ("source_chat_ids", "summary_of")
        for value in _front_matter_list(front_matter.get(key))
    }
    if source_chat_ids & context.excluded_chat_ids:
        return False

    serialized = document.document.body
    serialized += "\n" + "\n".join(
        f"{key}: {value}" for key, value in front_matter.items()
    )
    if context.prompt in serialized:
        return False

    for key in ("created_at", "updated_at"):
        timestamp = _parse_datetime(front_matter.get(key))
        if timestamp is not None and timestamp > context.cutoff:
            return False
    return True


def _front_matter_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a compact character-style benchmark from database history and "
            "render a report."
        )
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="Target user id. Defaults to the most recent user for the selected channel.",
    )
    parser.add_argument(
        "--channel",
        choices=("discord", "line"),
        default="discord",
        help="Chat channel to read history from.",
    )
    parser.add_argument(
        "--conversation-id",
        default=None,
        help="Target Discord conversation id. Defaults to the latest conversation.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=8,
        help="Maximum number of raw turns before the target prompt.",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Explicit user prompt. Defaults to the latest user message in history.",
    )
    parser.add_argument(
        "--openai-model",
        action="append",
        default=None,
        dest="openai_models",
        help="OpenAI model to evaluate. Repeat for multiple models.",
    )
    parser.add_argument(
        "--gemini-model",
        action="append",
        default=None,
        dest="gemini_models",
        help="Gemini model to evaluate. Repeat for multiple models.",
    )
    parser.add_argument(
        "--include-tools",
        action="store_true",
        help="Pass application tool definitions to providers; no tool loop is run.",
    )
    parser.add_argument(
        "--style-profile",
        choices=tuple(_STYLE_PROFILES),
        default="application",
        help="Prompt and provider parameter profile for the benchmark.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmarks") / "latest-run",
        help="Directory for JSONL and report outputs.",
    )
    parser.add_argument(
        "--model-order",
        action="append",
        default=None,
        dest="model_order",
        help="Preferred display order for models. Repeat to specify multiple values.",
    )
    return parser.parse_args()


async def main_async() -> None:
    load_dotenv(".env.local")
    args = _parse_args()
    database.init_db(os.environ["DATABASE_URL"])
    chat_type = ChatType.from_primitive(args.channel).unwrap()
    style_profile = _STYLE_PROFILES[args.style_profile]
    async for session in database.get_session():
        target_chat = await _find_target_chat(
            session,
            chat_type=chat_type,
            prompt=args.prompt.strip() if args.prompt else None,
            user_id=args.user_id,
            conversation_id=args.conversation_id,
        )
        user_id = target_chat.user_id
        prompt = _chat_text(target_chat)
        if not prompt:
            raise RuntimeError(f"Target chat {target_chat.id!r} has no text content")

        history = await _load_raw_history_before_target(
            session,
            chat_type=chat_type,
            target_chat=target_chat,
            prompt=prompt,
            limit=args.history_limit,
        )
        turn_context = _build_benchmark_turn_context(
            target_chat,
            chat_type=chat_type,
            history=history,
            prompt=prompt,
        )
        context = await _assemble_application_context(
            turn_context,
            user_id=user_id,
            chat_type=chat_type,
            cutoff=_chat_timestamp(target_chat),
            excluded_chat_ids=frozenset({target_chat.id or ""}),
        )
        context = _apply_style_profile(context, style_profile)
        records = await _run_models(
            context=context,
            openai_models=args.openai_models or _OPENAI_MODELS,
            gemini_models=args.gemini_models or _GEMINI_MODELS,
            include_tools=args.include_tools,
            style_profile=style_profile,
        )
        _write_outputs(
            args.output_dir,
            records,
            model_order=args.model_order,
        )
        break


async def _find_target_chat(
    session: AsyncSession,
    *,
    chat_type: ChatType,
    prompt: str | None,
    user_id: str | None,
    conversation_id: str | None,
) -> ChatORM:
    table = cast(Any, ChatORM).__table__
    conditions: list[Any] = [
        table.c.channel == chat_type.to_primitive().lower(),
        table.c.role == "user",
    ]
    if user_id is not None:
        conditions.append(table.c.user_id == user_id)
    if conversation_id is not None:
        conditions.append(table.c.external_conversation_id == conversation_id)
    result = await session.execute(
        select(ChatORM).where(*conditions).order_by(desc(table.c.accepted_sequence))
    )
    for chat in result.scalars().all():
        if prompt is None or _chat_text(chat) == prompt:
            return chat
    scope = f"channel={chat_type.to_primitive().lower()}"
    if user_id is not None:
        scope += f" user_id={user_id!r}"
    if conversation_id is not None:
        scope += f" conversation_id={conversation_id!r}"
    if prompt is not None:
        scope += " with the requested prompt"
    raise RuntimeError(f"No target user message found for {scope}")


def _chat_text(chat: ChatORM) -> str:
    payload = chat.message_content.get("payload")
    if not isinstance(payload, dict):
        return ""
    rendered = render_message_content_text(payload)
    return rendered.strip() if rendered is not None else ""


async def _load_raw_history_before_target(
    session: AsyncSession,
    *,
    chat_type: ChatType,
    target_chat: ChatORM,
    prompt: str,
    limit: int,
) -> list[ChatHistoryItem]:
    table = cast(Any, ChatORM).__table__
    result = await session.execute(
        select(ChatORM)
        .where(
            table.c.channel == chat_type.to_primitive().lower(),
            table.c.user_id == target_chat.user_id,
            table.c.external_conversation_id == target_chat.external_conversation_id,
            table.c.accepted_sequence < target_chat.accepted_sequence,
        )
        .order_by(desc(table.c.accepted_sequence))
        .limit(max(limit * 2, limit))
    )
    history = [
        _chat_history_item(chat, chat_type=chat_type)
        for chat in reversed(result.scalars().all())
    ]
    normalized_prompt = _normalize_text(prompt)
    return [
        item
        for item in history
        if not (
            item.role == "user" and _normalize_text(item.content) == normalized_prompt
        )
    ][-limit:]


def _chat_history_item(
    chat: ChatORM,
    *,
    chat_type: ChatType,
) -> ChatHistoryItem:
    role: Literal["user", "assistant", "system"]
    if chat.role == "assistant":
        role = "assistant"
    elif chat.role == "system":
        role = "system"
    else:
        role = "user"
    return ChatHistoryItem(
        id=chat.id or "",
        user_id=chat.user_id,
        chat_type=chat_type,
        role=role,
        content=_chat_text(chat),
        occurred_at=chat.created_at,
    )


def _build_benchmark_turn_context(
    target_chat: ChatORM,
    *,
    chat_type: ChatType,
    history: list[ChatHistoryItem],
    prompt: str,
) -> AgentTurnContext:
    session_history, boundary = latest_session_window(
        history,
        memory_boundary_at=None,
    )
    boundary_context = ConversationContext(
        chat_scope=(
            f"LINE user_id={target_chat.user_id}"
            if chat_type is ChatType.LINE
            else (
                "DISCORD "
                f"channel_id={target_chat.external_conversation_id} "
                f"user_id={target_chat.user_id}"
            )
        ),
        current_time=_chat_timestamp(target_chat),
        timezone="UTC",
        observed_message_count=len(session_history),
        has_session_boundary=boundary is not None,
        current_session_started_at=boundary[0] if boundary is not None else None,
        previous_message_at=boundary[1] if boundary is not None else None,
        gap_minutes=boundary[2] if boundary is not None else None,
    )
    return AgentTurnContext(
        prompt=prompt,
        recent_history=session_history,
        conversation=boundary_context,
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _chat_timestamp(chat: ChatORM) -> datetime:
    value = chat.created_at
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _assemble_application_context(
    turn_context: AgentTurnContext,
    *,
    user_id: str,
    chat_type: ChatType,
    cutoff: datetime,
    excluded_chat_ids: frozenset[str],
) -> BenchmarkContext:
    character_id = resolve_active_character_id()
    store = FilesystemMemoryStore(default_memory_root())
    profile_service = FilesystemAgentProfileService(store, character_id)
    session_factory = async_sessionmaker(
        database.get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )
    memory_index_query = _BenchmarkMemoryIndexQuery(
        delegate=SQLAlchemyMemoryIndexQuery(session_factory, store),
        cutoff=cutoff,
        excluded_chat_ids=excluded_chat_ids,
        prompt=turn_context.prompt,
    )
    memory_service = FilesystemMemoryService(
        memory_index_query,
        profile_service,
        character_id=character_id,
    )
    inference_context = AgentInferenceContextService(
        memory_service,
        profile_service,
        StaticToolCatalog(),
    )
    result = await inference_context.assemble(
        AgentInferenceContextRequest(
            turn_context=turn_context,
            user_id=user_id,
            character_id=character_id,
            chat_type=chat_type,
        )
    )
    if is_err(result):
        raise RuntimeError(f"Failed to assemble application context: {result.error}")
    system_prompt = compose_system_instruction(result.value)
    if system_prompt is None:
        raise RuntimeError("Application context did not produce a system instruction")
    return BenchmarkContext(
        system_prompt=system_prompt,
        history=tuple(result.value.recent_history),
        prompt=result.value.prompt,
        tool_definitions=tuple(result.value.tool_definitions),
    )


def _apply_style_profile(
    context: BenchmarkContext,
    style_profile: BenchmarkStyleProfile,
) -> BenchmarkContext:
    """Append benchmark-only style constraints to the app prompt."""

    if not style_profile.system_prompt_suffix:
        return context
    return BenchmarkContext(
        system_prompt="\n\n".join(
            [context.system_prompt, style_profile.system_prompt_suffix]
        ),
        history=context.history,
        prompt=context.prompt,
        tool_definitions=context.tool_definitions,
    )


async def _run_models(
    *,
    context: BenchmarkContext,
    openai_models: Sequence[str],
    gemini_models: Sequence[str],
    include_tools: bool = False,
    style_profile: BenchmarkStyleProfile | None = None,
) -> list[BenchmarkRecord]:
    """Run all selected providers concurrently with the same context."""

    active_style_profile = style_profile or _STYLE_PROFILES["application"]
    openai_client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    tool_definitions = list(context.tool_definitions) if include_tools else []
    tasks = [
        _run_openai_record(
            openai_client,
            context=context,
            model_id=model_id,
            tool_definitions=tool_definitions,
            style_profile=active_style_profile,
        )
        for model_id in openai_models
    ]
    tasks.extend(
        _run_gemini_record(
            gemini_client,
            context=context,
            model_id=model_id,
            tool_definitions=tool_definitions,
            style_profile=active_style_profile,
        )
        for model_id in gemini_models
    )
    try:
        return list(await asyncio.gather(*tasks))
    finally:
        await openai_client.close()


async def _run_openai_record(
    client: AsyncOpenAI,
    *,
    context: BenchmarkContext,
    model_id: str,
    tool_definitions: Sequence[ToolDefinition],
    style_profile: BenchmarkStyleProfile,
) -> BenchmarkRecord:
    """Run one OpenAI model and normalize its benchmark record."""

    started_at = datetime.now(tz=UTC)
    started_clock = perf_counter()
    try:
        raw_output, usage = await _call_openai(
            client,
            model_id=model_id,
            system_prompt=context.system_prompt,
            history=list(context.history),
            prompt=context.prompt,
            tool_definitions=tool_definitions,
            style_profile=style_profile,
        )
    except Exception as exc:  # pragma: no cover - live API guardrail
        raw_output = f"ERROR: {exc}"
        usage = {}
    return BenchmarkRecord(
        case_id="case-1",
        character_id=os.getenv("ACTIVE_CHARACTER_ID", "shirasagi-reina"),
        scenario_label="recent-chat-reply",
        memory_packet_id="application-inference-context",
        system_prompt=context.system_prompt,
        conversation_history=context.history,
        user_prompt=context.prompt,
        model_provider="openai",
        model_id=model_id,
        generation_params={
            "style_profile": style_profile.name,
            "max_output_tokens": _DEFAULT_OPENAI_MAX_OUTPUT_TOKENS,
            **(
                {"reasoning_effort": style_profile.openai_reasoning_effort}
                if style_profile.openai_reasoning_effort is not None
                else {}
            ),
            **(
                {"text_verbosity": style_profile.openai_text_verbosity}
                if style_profile.openai_text_verbosity is not None
                else {}
            ),
            "tool_definitions_in_request": [
                definition.name for definition in tool_definitions
            ],
        },
        raw_output=raw_output,
        created_at=started_at,
        token_usage=usage,
        latency_ms=round((perf_counter() - started_clock) * 1000),
    )


async def _run_gemini_record(
    client: genai.Client,
    *,
    context: BenchmarkContext,
    model_id: str,
    tool_definitions: Sequence[ToolDefinition],
    style_profile: BenchmarkStyleProfile,
) -> BenchmarkRecord:
    """Run one Gemini model and normalize its benchmark record."""

    started_at = datetime.now(tz=UTC)
    started_clock = perf_counter()
    try:
        raw_output, usage = await _call_gemini(
            client,
            model_id=model_id,
            system_prompt=context.system_prompt,
            history=list(context.history),
            prompt=context.prompt,
            tool_definitions=tool_definitions,
            style_profile=style_profile,
        )
    except Exception as exc:  # pragma: no cover - live API guardrail
        raw_output = f"ERROR: {exc}"
        usage = {}
    return BenchmarkRecord(
        case_id="case-1",
        character_id=os.getenv("ACTIVE_CHARACTER_ID", "shirasagi-reina"),
        scenario_label="recent-chat-reply",
        memory_packet_id="application-inference-context",
        system_prompt=context.system_prompt,
        conversation_history=context.history,
        user_prompt=context.prompt,
        model_provider="google",
        model_id=model_id,
        generation_params={
            "style_profile": style_profile.name,
            "max_output_tokens": _DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
            "thinking_level": _gemini_thinking_level(style_profile, model_id).value,
            **(
                {"temperature": style_profile.gemini_temperature}
                if style_profile.gemini_temperature is not None
                else {}
            ),
            "tool_definitions_in_request": [
                definition.name for definition in tool_definitions
            ],
        },
        raw_output=raw_output,
        created_at=started_at,
        token_usage=usage,
        latency_ms=round((perf_counter() - started_clock) * 1000),
    )


async def _call_openai(
    client: AsyncOpenAI,
    *,
    model_id: str,
    system_prompt: str,
    history: list[ChatHistoryItem],
    prompt: str,
    tool_definitions: Sequence[ToolDefinition],
    style_profile: BenchmarkStyleProfile,
) -> tuple[str, dict[str, Any]]:
    input_messages: list[dict[str, str]] = [
        {"role": item.role, "content": item.content} for item in history
    ]
    input_messages.append({"role": "user", "content": prompt})
    request_kwargs: dict[str, Any] = {
        "model": model_id,
        "instructions": system_prompt,
        "input": cast(list[ResponseInputItemParam], input_messages),
        "store": False,
        "max_output_tokens": _DEFAULT_OPENAI_MAX_OUTPUT_TOKENS,
    }
    provider_tools = _openai_tools(bind_provider_tools(list(tool_definitions)))
    if provider_tools:
        request_kwargs["tools"] = provider_tools
    if style_profile.openai_reasoning_effort is not None:
        request_kwargs["reasoning"] = {
            "effort": style_profile.openai_reasoning_effort,
        }
    if style_profile.openai_text_verbosity is not None:
        request_kwargs["text"] = {
            "verbosity": style_profile.openai_text_verbosity,
        }
    response = await client.responses.create(**request_kwargs)
    usage: dict[str, Any] = {}
    if response.usage is not None:
        usage = response.usage.model_dump(mode="json")
    return response.output_text or "", usage


async def _call_gemini(
    client: genai.Client,
    *,
    model_id: str,
    system_prompt: str,
    history: list[ChatHistoryItem],
    prompt: str,
    tool_definitions: Sequence[ToolDefinition],
    style_profile: BenchmarkStyleProfile,
) -> tuple[str, dict[str, Any]]:
    contents: list[types.Content] = []
    for item in history:
        role = "user" if item.role == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=item.content)]))

    async def operation() -> tuple[str, dict[str, Any]]:
        thinking_level = _gemini_thinking_level(style_profile, model_id)
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt,
            "max_output_tokens": _DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
            "thinking_config": types.ThinkingConfig(
                thinking_level=thinking_level,
            ),
        }
        if style_profile.gemini_temperature is not None:
            config_kwargs["temperature"] = style_profile.gemini_temperature
        config = types.GenerateContentConfig(**config_kwargs)
        provider_tools = _gemini_tools(bind_provider_tools(list(tool_definitions)))
        if provider_tools:
            config.tools = provider_tools
        response = await client.aio.models.generate_content(
            model=model_id,
            contents=contents
            + [types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )
        usage: dict[str, Any] = {}
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata is not None:
            usage = usage_metadata.model_dump(mode="json")
        usage.update(_gemini_response_metadata(response))
        text = response.text or _extract_gemini_text(response)
        if not text.strip():
            raise RuntimeError("Gemini returned an empty response")
        return text, usage

    return await _retry_gemini(operation)


def _gemini_thinking_level(
    style_profile: BenchmarkStyleProfile,
    model_id: str,
) -> types.ThinkingLevel:
    """Select the supported thinking level for a Gemini model family."""

    if "pro" in model_id:
        return style_profile.gemini_pro_thinking_level
    return style_profile.gemini_flash_thinking_level


def _gemini_response_metadata(response: Any) -> dict[str, Any]:
    """Extract response metadata needed to diagnose incomplete generations."""

    metadata: dict[str, Any] = {}
    model_version = getattr(response, "model_version", None)
    if isinstance(model_version, str) and model_version:
        metadata["model_version"] = model_version

    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, list) or not candidates:
        return metadata
    candidate = candidates[0]
    finish_reason = _enum_value(getattr(candidate, "finish_reason", None))
    if finish_reason is not None:
        metadata["finish_reason"] = finish_reason
    finish_message = getattr(candidate, "finish_message", None)
    if isinstance(finish_message, str) and finish_message:
        metadata["finish_message"] = finish_message
    return metadata


def _enum_value(value: Any) -> str | None:
    """Return a stable string for SDK enum-like values."""

    if isinstance(value, str):
        return value
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    raw_value = getattr(value, "value", None)
    if isinstance(raw_value, str) and raw_value:
        return raw_value
    return None


def _extract_gemini_text(response: Any) -> str:
    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, list) or not candidates:
        return ""
    candidate = candidates[0]
    content = getattr(candidate, "content", None)
    parts = getattr(content, "parts", None)
    if not isinstance(parts, list):
        return ""
    texts: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if isinstance(text, str) and text.strip():
            texts.append(text)
    return "\n".join(texts)


async def _retry_gemini(
    operation: Any,
) -> tuple[str, dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, _GEMINI_RETRY_ATTEMPTS + 1):
        try:
            return await operation()
        except Exception as exc:  # pragma: no cover - live API guardrail
            last_error = exc
            if attempt >= _GEMINI_RETRY_ATTEMPTS:
                raise
            await asyncio.sleep(_GEMINI_RETRY_DELAY_SECONDS * attempt)
    assert last_error is not None
    raise last_error


def _write_outputs(
    output_dir: Path,
    records: list[BenchmarkRecord],
    *,
    model_order: list[str] | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "benchmark.jsonl"
    markdown_path = output_dir / "benchmark.report.md"
    html_path = output_dir / "benchmark.report.html"
    jsonl_path.write_text(
        "\n".join(_record_to_json(record) for record in records) + "\n",
        encoding="utf-8",
    )
    report = write_benchmark_reports(
        records,
        markdown_path=markdown_path,
        html_path=html_path,
        model_order=model_order,
        title="Character Benchmark Report",
    )
    print(
        f"Wrote {jsonl_path}, {markdown_path}, and {html_path} "
        f"for {report.total_records} responses across {report.total_cases} case(s)."
    )
    for record in records:
        raw_text = str(record.raw_output)
        print(
            f"- {record.model_provider} / {record.model_id}: "
            f"{raw_text[:120].replace(chr(10), ' ')}"
        )


def _record_to_json(record: BenchmarkRecord) -> str:
    payload = {
        "case_id": record.case_id,
        "character_id": record.character_id,
        "scenario_label": record.scenario_label,
        "memory_packet_id": record.memory_packet_id,
        "system_prompt": record.system_prompt,
        "conversation_history": [
            item.model_dump(mode="json") for item in record.conversation_history
        ],
        "user_prompt": record.user_prompt,
        "model_provider": record.model_provider,
        "model_id": record.model_id,
        "generation_params": record.generation_params,
        "raw_output": record.raw_output,
        "created_at": (
            record.created_at.isoformat() if record.created_at is not None else None
        ),
        "token_usage": record.token_usage,
        "latency_ms": record.latency_ms,
    }
    return json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    asyncio.run(main_async())
