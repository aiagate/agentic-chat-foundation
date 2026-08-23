"""Tests for the deterministic embedding adapter."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from flow_res import is_err

from app.infrastructure.memory.embedding import (
    DeterministicEmbeddingService,
    GeminiEmbeddingService,
    embed_text_deterministically,
    embed_texts_deterministically,
)


@pytest.mark.anyio
async def test_deterministic_embedding_service_returns_stable_vectors() -> None:
    """The fake embedding adapter should be stable and deterministic."""
    service = DeterministicEmbeddingService(dimension=8)

    result = await service.embed_texts(["memory index", "memory index"])

    assert not is_err(result)
    assert len(result.value) == 2
    assert result.value[0] == result.value[1]
    assert len(result.value[0]) == 8


def test_deterministic_embedding_helpers_match_service_output() -> None:
    """The sync helpers should match the deterministic adapter semantics."""
    vectors = embed_texts_deterministically(
        ["memory index", ""],
        dimension=8,
    )

    assert vectors[0] == embed_text_deterministically("memory index", dimension=8)
    assert vectors[1] == [0.0] * 8


@pytest.mark.anyio
async def test_gemini_embedding_service_uses_embedding_2_per_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding 2 receives one task-prefixed text per request."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    embed_mock = AsyncMock(
        side_effect=[
            SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2])]),
            SimpleNamespace(embeddings=[SimpleNamespace(values=[0.3, 0.4])]),
        ]
    )

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.aio = SimpleNamespace(
                models=SimpleNamespace(embed_content=embed_mock),
            )

    monkeypatch.setattr(
        "app.infrastructure.memory.embedding.genai.Client",
        FakeClient,
    )

    service = GeminiEmbeddingService(output_dimensionality=2)
    result = await service.embed_texts(["first", "second"])

    assert not is_err(result)
    assert result.value == [[0.1, 0.2], [0.3, 0.4]]
    assert embed_mock.await_count == 2
    first_call = embed_mock.await_args_list[0].kwargs
    second_call = embed_mock.await_args_list[1].kwargs
    assert first_call["model"] == "gemini-embedding-2"
    assert second_call["model"] == "gemini-embedding-2"
    assert first_call["contents"] == "task: sentence similarity | query: first"
    assert second_call["contents"] == "task: sentence similarity | query: second"
    config = first_call["config"]
    assert config.task_type is None
    assert config.output_dimensionality == 2


@pytest.mark.anyio
async def test_gemini_embedding_service_returns_empty_for_empty_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty batches should not make a remote request."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    embed_mock = AsyncMock()

    class FakeClient:
        def __init__(self, api_key: str | None) -> None:
            self.aio = SimpleNamespace(
                models=SimpleNamespace(embed_content=embed_mock),
            )

    monkeypatch.setattr(
        "app.infrastructure.memory.embedding.genai.Client",
        FakeClient,
    )

    result = await GeminiEmbeddingService().embed_texts([])

    assert not is_err(result)
    assert result.value == []
    embed_mock.assert_not_awaited()
