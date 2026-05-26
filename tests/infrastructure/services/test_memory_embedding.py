"""Tests for the deterministic embedding adapter."""

import pytest
from flow_res import is_err

from app.infrastructure.services.memory_embedding import (
    DeterministicEmbeddingService,
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
