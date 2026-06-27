"""Run a small benchmark from database chat history and render a report."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.messages.chat_history import ChatHistoryItem
from app.infrastructure import database
from app.infrastructure.benchmark.report import (
    BenchmarkRecord,
    write_benchmark_reports,
)
from app.infrastructure.memory.markdown import parse_memory_markdown
from app.infrastructure.queries.chat_history_query import SQLAlchemyChatHistoryQuery
from app.infrastructure.queries.raw_chat_log_query import SQLAlchemyRawChatLogQuery

_OPENAI_MODELS = ("gpt-5.5", "gpt-5.4")
_GEMINI_MODELS = ("gemini-3.5-flash", "gemini-2.5-pro")
_DEFAULT_HISTORY_LIMIT = 8
_DEFAULT_MAX_OUTPUT_TOKENS = 1024
_DEFAULT_TEMPERATURE = 0.7
_GEMINI_RETRY_ATTEMPTS = 3
_GEMINI_RETRY_DELAY_SECONDS = 2.0


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
        help="Target user id. Defaults to the most recent available Discord user.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=_DEFAULT_HISTORY_LIMIT,
        help="Maximum number of chat turns to include in the prompt window.",
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
    args = _parse_args()
    database.init_db(os.environ["DATABASE_URL"])
    async for session in database.get_session():
        user_id = args.user_id or await _pick_latest_user_id(session)
        history = await _load_history(session, user_id, limit=args.history_limit)
        if not history:
            raise RuntimeError(f"No chat history found for user id {user_id!r}")

        prompt = _last_user_prompt(history)
        prompt_history = history[:-1]
        system_prompt = _build_system_prompt()
        records = await _run_models(
            prompt=prompt,
            history=prompt_history,
            system_prompt=system_prompt,
        )
        _write_outputs(
            args.output_dir,
            records,
            model_order=args.model_order,
        )
        break


async def _pick_latest_user_id(session: AsyncSession) -> str:
    query = SQLAlchemyRawChatLogQuery(session)
    result = await query.list_memory_sleep_source_user_ids(limit=20)
    if result.__class__.__name__ != "Ok" or not result.value:
        raise RuntimeError("No user ids available in chat history")
    return result.value[0]


async def _load_history(
    session: AsyncSession,
    user_id: str,
    *,
    limit: int,
) -> list[ChatHistoryItem]:
    query = SQLAlchemyChatHistoryQuery(session)
    result = await query.get_recent_history(
        chat_type=_guess_chat_type(),
        user_id=user_id,
        limit=limit,
    )
    if result.__class__.__name__ != "Ok":
        raise RuntimeError(f"Failed to load history for user id {user_id!r}")
    return result.value


def _guess_chat_type() -> Any:
    from app.domain.value_objects.chat_type import ChatType

    return ChatType.DISCORD


def _last_user_prompt(history: list[ChatHistoryItem]) -> str:
    for item in reversed(history):
        if item.role == "user" and item.content.strip():
            return item.content.strip()
    raise RuntimeError("History does not contain a user prompt")


def _build_system_prompt() -> str:
    character_id = os.getenv("ACTIVE_CHARACTER_ID", "shirasagi-reina")
    memory_root = Path("memory") / "profiles" / "agent" / character_id
    parts: list[str] = []
    for part_name in ("AGENTS", "SOUL", "PERSONAL", "MEMORY"):
        part_path = memory_root / f"{part_name}.md"
        if not part_path.exists():
            raise FileNotFoundError(
                f"Missing memory profile file: {part_path}. "
                "The benchmark should use the real memory/ prompt."
            )
        document = parse_memory_markdown(
            part_path.read_text(encoding="utf-8"),
            location=str(part_path),
        )
        parts.append(document.body.strip())
    return "\n\n".join(part for part in parts if part).strip()


async def _run_models(
    *,
    prompt: str,
    history: list[ChatHistoryItem],
    system_prompt: str,
) -> list[BenchmarkRecord]:
    openai_client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    records: list[BenchmarkRecord] = []
    for model_id in _OPENAI_MODELS:
        started_at = datetime.now(tz=UTC)
        try:
            raw_output, usage = await _call_openai(
                openai_client,
                model_id=model_id,
                system_prompt=system_prompt,
                history=history,
                prompt=prompt,
            )
        except Exception as exc:  # pragma: no cover - live API guardrail
            raw_output = f"ERROR: {exc}"
            usage = {}
        records.append(
            BenchmarkRecord(
                case_id="case-1",
                character_id=os.getenv("ACTIVE_CHARACTER_ID", "shirasagi-reina"),
                scenario_label="recent-chat-reply",
                memory_packet_id="memory/profiles/agent/shirasagi-reina",
                system_prompt=system_prompt,
                conversation_history=tuple(history),
                user_prompt=prompt,
                model_provider="openai",
                model_id=model_id,
                generation_params={
                    "max_output_tokens": _DEFAULT_MAX_OUTPUT_TOKENS,
                },
                raw_output=raw_output,
                created_at=started_at,
                token_usage=usage,
                latency_ms=None,
            )
        )
    for model_id in _GEMINI_MODELS:
        started_at = datetime.now(tz=UTC)
        try:
            raw_output, usage = await _call_gemini(
                gemini_client,
                model_id=model_id,
                system_prompt=system_prompt,
                history=history,
                prompt=prompt,
            )
        except Exception as exc:  # pragma: no cover - live API guardrail
            raw_output = f"ERROR: {exc}"
            usage = {}
        records.append(
            BenchmarkRecord(
                case_id="case-1",
                character_id=os.getenv("ACTIVE_CHARACTER_ID", "shirasagi-reina"),
                scenario_label="recent-chat-reply",
                memory_packet_id="memory/profiles/agent/shirasagi-reina",
                system_prompt=system_prompt,
                conversation_history=tuple(history),
                user_prompt=prompt,
                model_provider="google",
                model_id=model_id,
                generation_params={
                    "temperature": _DEFAULT_TEMPERATURE,
                    "max_output_tokens": _DEFAULT_MAX_OUTPUT_TOKENS,
                },
                raw_output=raw_output,
                created_at=started_at,
                token_usage=usage,
                latency_ms=None,
            )
        )
    return records


async def _call_openai(
    client: AsyncOpenAI,
    *,
    model_id: str,
    system_prompt: str,
    history: list[ChatHistoryItem],
    prompt: str,
) -> tuple[str, dict[str, Any]]:
    input_messages: list[dict[str, str]] = [
        {"role": item.role, "content": item.content} for item in history
    ]
    input_messages.append({"role": "user", "content": prompt})
    response = await client.responses.create(
        model=model_id,
        instructions=system_prompt,
        input=input_messages,
        store=False,
        max_output_tokens=_DEFAULT_MAX_OUTPUT_TOKENS,
    )
    usage = {}
    if getattr(response, "usage", None) is not None:
        usage = response.usage.model_dump(mode="json")
    return response.output_text or "", usage


async def _call_gemini(
    client: genai.Client,
    *,
    model_id: str,
    system_prompt: str,
    history: list[ChatHistoryItem],
    prompt: str,
) -> tuple[str, dict[str, Any]]:
    contents: list[types.Content] = []
    for item in history:
        role = "user" if item.role == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=item.content)]))

    async def operation() -> tuple[str, dict[str, Any]]:
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt,
            "temperature": _DEFAULT_TEMPERATURE,
            "max_output_tokens": _DEFAULT_MAX_OUTPUT_TOKENS,
        }
        if "flash" in model_id:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW,
            )
        response = await client.aio.models.generate_content(
            model=model_id,
            contents=contents
            + [types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(**config_kwargs),
        )
        usage: dict[str, Any] = {}
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata is not None:
            usage = usage_metadata.model_dump(mode="json")
        text = response.text or _extract_gemini_text(response)
        if not text.strip():
            raise RuntimeError("Gemini returned an empty response")
        return text, usage

    return await _retry_gemini(operation)


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
