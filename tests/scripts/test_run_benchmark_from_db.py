"""Tests for the database-backed model benchmark runner."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest

import scripts.run_benchmark_from_db as benchmark


@pytest.mark.anyio
async def test_run_models_starts_all_provider_calls_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every selected model should receive the same context in parallel."""

    active_calls = 0
    started_calls = 0
    release = asyncio.Event()

    class FakeOpenAIClient:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key

        async def close(self) -> None:
            return None

    class FakeGeminiClient:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key

    async def fake_openai_call(
        client: Any,
        *,
        model_id: str,
        system_prompt: str,
        history: list[Any],
        prompt: str,
        tool_definitions: list[Any],
        style_profile: Any,
    ) -> tuple[str, dict[str, Any]]:
        nonlocal active_calls, started_calls
        assert system_prompt == "system"
        assert history == []
        assert prompt == "target"
        assert tool_definitions == []
        active_calls += 1
        started_calls += 1
        if started_calls == 4:
            release.set()
        await release.wait()
        active_calls -= 1
        return f"openai:{model_id}", {"model": model_id}

    async def fake_gemini_call(
        client: Any,
        *,
        model_id: str,
        system_prompt: str,
        history: list[Any],
        prompt: str,
        tool_definitions: list[Any],
        style_profile: Any,
    ) -> tuple[str, dict[str, Any]]:
        nonlocal active_calls, started_calls
        assert system_prompt == "system"
        assert history == []
        assert prompt == "target"
        assert tool_definitions == []
        active_calls += 1
        started_calls += 1
        if started_calls == 4:
            release.set()
        await release.wait()
        active_calls -= 1
        return f"gemini:{model_id}", {"model": model_id}

    monkeypatch.setattr(benchmark, "AsyncOpenAI", FakeOpenAIClient)
    monkeypatch.setattr(benchmark.genai, "Client", FakeGeminiClient)
    monkeypatch.setattr(benchmark, "_call_openai", fake_openai_call)
    monkeypatch.setattr(benchmark, "_call_gemini", fake_gemini_call)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    context = benchmark.BenchmarkContext(
        system_prompt="system",
        history=(),
        prompt="target",
    )
    records = await benchmark._run_models(
        context=context,
        openai_models=("gpt-a", "gpt-b", "gpt-c"),
        gemini_models=("gemini-a",),
    )

    assert started_calls == 4
    assert active_calls == 0
    assert len(records) == 4
    assert [record.model_id for record in records] == [
        "gpt-a",
        "gpt-b",
        "gpt-c",
        "gemini-a",
    ]
    assert all(record.conversation_history == () for record in records)
    assert all(record.latency_ms is not None for record in records)


@pytest.mark.anyio
async def test_call_gemini_uses_app_budget_and_records_finish_metadata() -> None:
    """Gemini benchmark calls should match app generation settings."""

    captured: dict[str, Any] = {}

    class FakeUsage:
        def model_dump(self, **_: Any) -> dict[str, int]:
            return {
                "prompt_token_count": 10,
                "thoughts_token_count": 12,
                "candidates_token_count": 3,
            }

    class FakeModels:
        async def generate_content(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                text="short response",
                model_version="gemini-test-version",
                usage_metadata=FakeUsage(),
                candidates=[
                    SimpleNamespace(
                        finish_reason=benchmark.types.FinishReason.MAX_TOKENS,
                        finish_message="maximum output reached",
                    )
                ],
            )

    client = cast(
        benchmark.genai.Client,
        SimpleNamespace(aio=SimpleNamespace(models=FakeModels())),
    )
    text, usage = await benchmark._call_gemini(
        client,
        model_id="gemini-3.1-pro-preview",
        system_prompt="system",
        history=[],
        prompt="target",
        tool_definitions=[],
        style_profile=benchmark._STYLE_PROFILES["human-sns"],
    )

    config = captured["config"]
    assert text == "short response"
    assert config.max_output_tokens == 2048
    assert config.thinking_config.thinking_level == benchmark.types.ThinkingLevel.LOW
    assert usage["finish_reason"] == "MAX_TOKENS"
    assert usage["finish_message"] == "maximum output reached"
    assert usage["model_version"] == "gemini-test-version"


def test_gemini_3_6_flash_uses_supported_medium_thinking_level() -> None:
    """Gemini 3.6 Flash requires a medium or high thinking level."""

    assert (
        benchmark._gemini_thinking_level(
            benchmark._STYLE_PROFILES["human-sns"],
            "gemini-3.6-flash",
        )
        == benchmark.types.ThinkingLevel.MEDIUM
    )
