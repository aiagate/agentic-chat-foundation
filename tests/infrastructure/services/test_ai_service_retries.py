"""Tests for AI service retry behavior."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from flow_res import is_err

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
