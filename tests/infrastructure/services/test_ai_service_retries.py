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
from app.contracts.messages.tool_contracts import ToolDefinition
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.services.gemini_service import GeminiService
from app.infrastructure.services.gpt_service import GptService


@pytest.mark.anyio
async def test_gemini_service_retries_three_times_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that Gemini retries transient failures up to three times."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = SimpleNamespace(parsed={"contents": ["retry ok"]}, text=None)
    generate_mock = AsyncMock(
        side_effect=[
            RuntimeError("attempt-1"),
            RuntimeError("attempt-2"),
            RuntimeError("attempt-3"),
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

    service = GeminiService()
    result = await service.generate_content(
        prompt="hello",
        history=[],
    )

    assert not is_err(result)
    assert result.value.contents == ["retry ok"]
    assert generate_mock.await_count == 4


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
        "timeline_patch": None,
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
async def test_gemini_service_normalizes_scalar_contents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that Gemini scalar contents are normalized into a list."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = SimpleNamespace(
        parsed=None,
        text=json.dumps(
            {
                "contents": "ええ、よくわかります。夕暮れ時は一日の疲れが出始める頃です。",
            }
        ),
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
    assert result.value.contents == [
        "ええ、よくわかります。夕暮れ時は一日の疲れが出始める頃です。"
    ]


@pytest.mark.anyio
async def test_gemini_service_normalizes_legacy_tool_call_arrays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that Gemini tool-call arrays are converted into canonical tool calls."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = SimpleNamespace(
        parsed=None,
        text=json.dumps(
            [
                {
                    "id": "call_1",
                    "name": "line.send",
                    "arguments": {
                        "contents": ["こんにちは。"]
                    },
                }
            ]
        ),
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
    assert result.value.contents == []
    assert len(result.value.tool_calls) == 1
    assert result.value.tool_calls[0].tool_call_id == "call_1"
    assert result.value.tool_calls[0].tool_name == "line.send"


@pytest.mark.anyio
async def test_gemini_service_normalizes_single_item_wrappers_with_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that Gemini wrapper arrays with tool calls are normalized."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = SimpleNamespace(
        parsed=None,
        text=json.dumps(
            [
                {
                    "contents": [],
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "name": "memory.read",
                            "arguments": {
                                "memory_id": "entity:memory-lookup",
                            },
                        }
                    ],
                }
            ]
        ),
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
    assert result.value.contents == []
    assert len(result.value.tool_calls) == 1
    assert result.value.tool_calls[0].tool_call_id == "call_1"
    assert result.value.tool_calls[0].tool_name == "memory.read"


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
    assert any("Gemini response accepted:" in record.message for record in caplog.records)


@pytest.mark.anyio
async def test_gpt_service_retries_three_times_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that OpenAI retries transient failures up to three times."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = SimpleNamespace(output_text=json.dumps({"contents": ["retry ok"]}))
    create_mock = AsyncMock(
        side_effect=[
            RuntimeError("attempt-1"),
            RuntimeError("attempt-2"),
            RuntimeError("attempt-3"),
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

    service = GptService()
    result = await service.generate_content(
        prompt="hello",
        history=[],
    )

    assert not is_err(result)
    assert result.value.contents == ["retry ok"]
    assert create_mock.await_count == 4


@pytest.mark.anyio
async def test_gpt_service_logs_full_request_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that OpenAI logs the full request context before the API call."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = SimpleNamespace(output_text=json.dumps({"contents": ["retry ok"]}))
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
