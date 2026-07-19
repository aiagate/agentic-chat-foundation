"""Tests for AI service retry behavior."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_res import is_err

from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.tool_contracts import ToolDefinition
from app.infrastructure.services.gemini_service import GeminiService
from app.infrastructure.services.gpt_service import GptService


@pytest.mark.anyio
async def test_gemini_service_retries_with_exponential_backoff_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that Gemini retries transient failures with backoff."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = SimpleNamespace(parsed={"contents": ["retry ok"]}, text=None)
    sleep_mock = AsyncMock(return_value=None)
    generate_mock = AsyncMock(
        side_effect=[
            RuntimeError("attempt-1"),
            RuntimeError("attempt-2"),
            RuntimeError("attempt-3"),
            RuntimeError("attempt-4"),
            response,
        ]
    )

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.aio = SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_mock)
            )

    monkeypatch.setattr(
        "app.infrastructure.services.gemini_service.genai.Client",
        FakeClient,
    )
    monkeypatch.setattr(
        "app.infrastructure.services.retry_support.asyncio.sleep",
        sleep_mock,
    )

    service = GeminiService()
    result = await service.generate_content(
        prompt="hello",
        history=[],
    )

    assert not is_err(result)
    assert result.value.contents == ["retry ok"]
    assert generate_mock.await_count == 5
    assert [record.args[0] for record in sleep_mock.await_args_list] == [
        1.0,
        2.0,
        4.0,
        8.0,
    ]


@pytest.mark.anyio
async def test_gemini_service_falls_back_to_raw_text_when_structured_output_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that Gemini uses raw text when parsed structured output is empty."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = SimpleNamespace(
        parsed={"contents": []},
        text=json.dumps({"contents": ["retry ok"]}),
    )
    generate_mock = AsyncMock(return_value=response)

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.aio = SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_mock)
            )

    monkeypatch.setattr(
        "app.infrastructure.services.gemini_service.genai.Client",
        FakeClient,
    )

    service = GeminiService()
    result = await service.generate_content(
        prompt="hello",
        history=[],
    )

    assert not is_err(result)
    assert result.value.contents == ["retry ok"]
    assert generate_mock.await_count == 1


@pytest.mark.anyio
async def test_gemini_service_wraps_direct_structured_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that direct structured Gemini output is normalized into content text."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    direct_payload = {
        "sections": [],
        "entity_patches": [],
        "profile_patch": None,
        "evidence": {"notes": ["ok"]},
    }
    response = SimpleNamespace(parsed=None, text=json.dumps(direct_payload))
    generate_mock = AsyncMock(return_value=response)

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.aio = SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_mock)
            )

    monkeypatch.setattr(
        "app.infrastructure.services.gemini_service.genai.Client",
        FakeClient,
    )

    service = GeminiService()
    result = await service.generate_content(
        prompt="hello",
        history=[],
    )

    assert not is_err(result)
    assert result.value.contents == [json.dumps(direct_payload, ensure_ascii=False)]


@pytest.mark.anyio
async def test_gemini_service_uses_gemini_3_5_flash_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the default Gemini model and thinking level match Gemini 3.5."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    recorded: dict[str, object] = {}
    response = SimpleNamespace(parsed={"contents": ["retry ok"]}, text=None)

    async def generate_mock(*args: object, **kwargs: object) -> object:
        recorded["kwargs"] = kwargs
        return response

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.aio = SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_mock)
            )

    monkeypatch.setattr(
        "app.infrastructure.services.gemini_service.genai.Client",
        FakeClient,
    )

    service = GeminiService()
    result = await service.generate_content(
        prompt="hello",
        history=[],
    )

    assert not is_err(result)
    kwargs = cast(dict[str, object], recorded["kwargs"])
    assert kwargs["model"] == "gemini-3.5-flash"
    config = cast(Any, kwargs["config"])
    assert config.thinking_config.thinking_level.value.lower() == "low"


@pytest.mark.anyio
async def test_gemini_service_logs_full_request_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that Gemini logs the full request context before the API call."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = SimpleNamespace(parsed={"contents": ["retry ok"]}, text=None)
    generate_mock = AsyncMock(return_value=response)

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.aio = SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_mock)
            )

    monkeypatch.setattr(
        "app.infrastructure.services.gemini_service.genai.Client",
        FakeClient,
    )

    service = GeminiService()
    with caplog.at_level(
        logging.INFO,
        logger="app.infrastructure.services.gemini_service",
    ):
        result = await service.generate_content(
            prompt="hello world from gemini",
            history=[
                ChatHistoryItem(
                    id="sys-1",
                    chat_type=ChatType.DISCORD,
                    role="system",
                    content="system context",
                ),
                ChatHistoryItem(
                    id="user-1",
                    chat_type=ChatType.DISCORD,
                    role="user",
                    content="user context",
                ),
            ],
            system_instruction="base system instruction",
            tool_definitions=[
                ToolDefinition(
                    name="memory.read",
                    description="Read memory.",
                    arguments_schema={"type": "object"},
                    result_schema={"type": "object"},
                    capability_scope=["memory"],
                    side_effect="read",
                    timeout_seconds=30,
                    max_calls_per_run=3,
                )
            ],
        )

    assert not is_err(result)
    assert any("Gemini request context:" in record.message for record in caplog.records)
    assert any("hello world from gemini" in record.message for record in caplog.records)
    assert any("system context" in record.message for record in caplog.records)
    assert any("base system instruction" in record.message for record in caplog.records)
    assert any('"name": "memory.read"' in record.message for record in caplog.records)
    assert any(
        "Gemini response accepted:" in record.message for record in caplog.records
    )


@pytest.mark.anyio
async def test_gpt_service_retries_with_exponential_backoff_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that OpenAI retries transient failures with backoff."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = SimpleNamespace(output_text="retry ok", output=[])
    sleep_mock = AsyncMock(return_value=None)
    create_mock = AsyncMock(
        side_effect=[
            RuntimeError("attempt-1"),
            RuntimeError("attempt-2"),
            RuntimeError("attempt-3"),
            RuntimeError("attempt-4"),
            response,
        ]
    )

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.responses = SimpleNamespace(create=create_mock)

    monkeypatch.setattr(
        "app.infrastructure.services.gpt_service.AsyncOpenAI",
        FakeClient,
    )
    monkeypatch.setattr(
        "app.infrastructure.services.retry_support.asyncio.sleep",
        sleep_mock,
    )

    service = GptService()
    result = await service.generate_content(
        prompt="hello",
        history=[],
    )

    assert not is_err(result)
    assert result.value.contents == ["retry ok"]
    assert create_mock.await_count == 5
    assert [record.args[0] for record in sleep_mock.await_args_list] == [
        1.0,
        2.0,
        4.0,
        8.0,
    ]


@pytest.mark.anyio
async def test_gpt_service_normalizes_native_function_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI provider aliases should normalize to canonical application tools."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = SimpleNamespace(
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                name="tool_0",
                arguments=json.dumps({"memory_id": "entity:example"}),
            )
        ],
    )
    create_mock = AsyncMock(return_value=response)

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.responses = SimpleNamespace(create=create_mock)

    monkeypatch.setattr(
        "app.infrastructure.services.gpt_service.AsyncOpenAI",
        FakeClient,
    )

    service = GptService()
    result = await service.generate_content(
        prompt="read memory",
        history=[],
        tool_definitions=[
            ToolDefinition(
                name="memory.read",
                description="Read memory.",
                arguments_schema={
                    "type": "object",
                    "properties": {"memory_id": {"type": "string"}},
                    "required": ["memory_id"],
                    "additionalProperties": False,
                },
            )
        ],
    )

    assert not is_err(result)
    assert result.value.contents == []
    assert result.value.tool_calls[0].tool_name == "memory.read"
    assert result.value.tool_calls[0].arguments == {"memory_id": "entity:example"}
    openai_call = create_mock.await_args
    assert openai_call is not None
    request = openai_call.kwargs
    assert request["tools"][0]["name"] == "tool_0"
    assert request["reasoning"] == {"effort": "low"}
    assert request["text"] == {"verbosity": "low"}
    assert request["max_output_tokens"] == 1024


@pytest.mark.anyio
async def test_gemini_service_normalizes_native_function_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemini function calls should normalize to canonical application tools."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = SimpleNamespace(
        parsed=None,
        text=None,
        function_calls=[
            SimpleNamespace(name="tool_0", args={"memory_id": "entity:example"})
        ],
    )
    generate_mock = AsyncMock(return_value=response)

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.aio = SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_mock)
            )

    monkeypatch.setattr(
        "app.infrastructure.services.gemini_service.genai.Client",
        FakeClient,
    )

    service = GeminiService()
    result = await service.generate_content(
        prompt="read memory",
        history=[],
        tool_definitions=[
            ToolDefinition(
                name="memory.read",
                description="Read memory.",
                arguments_schema={
                    "type": "object",
                    "properties": {"memory_id": {"type": "string"}},
                    "required": ["memory_id"],
                    "additionalProperties": False,
                },
            )
        ],
    )

    assert not is_err(result)
    assert result.value.tool_calls[0].tool_name == "memory.read"
    gemini_call = generate_mock.await_args
    assert gemini_call is not None
    config = gemini_call.kwargs["config"]
    assert config.automatic_function_calling.disable is True
    assert config.response_mime_type is None


@pytest.mark.anyio
async def test_gpt_service_logs_full_request_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that OpenAI logs the full request context before the API call."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = SimpleNamespace(output_text="retry ok", output=[])
    create_mock = AsyncMock(return_value=response)

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.responses = SimpleNamespace(create=create_mock)

    monkeypatch.setattr(
        "app.infrastructure.services.gpt_service.AsyncOpenAI",
        FakeClient,
    )

    service = GptService()
    with caplog.at_level(
        logging.INFO,
        logger="app.infrastructure.services.gpt_service",
    ):
        result = await service.generate_content(
            prompt="hello world from openai",
            history=[
                ChatHistoryItem(
                    id="sys-1",
                    chat_type=ChatType.DISCORD,
                    role="system",
                    content="system context",
                ),
                ChatHistoryItem(
                    id="user-1",
                    chat_type=ChatType.DISCORD,
                    role="user",
                    content="user context",
                ),
            ],
            system_instruction="base system instruction",
            tool_definitions=[
                ToolDefinition(
                    name="memory.read",
                    description="Read memory.",
                    arguments_schema={"type": "object"},
                    result_schema={"type": "object"},
                    capability_scope=["memory"],
                    side_effect="read",
                    timeout_seconds=30,
                    max_calls_per_run=3,
                )
            ],
        )

    assert not is_err(result)
    assert any("OpenAI request context:" in record.message for record in caplog.records)
    assert any("hello world from openai" in record.message for record in caplog.records)
    assert any("system context" in record.message for record in caplog.records)
    assert any("base system instruction" in record.message for record in caplog.records)
    assert any('"name": "memory.read"' in record.message for record in caplog.records)
