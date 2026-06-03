"""Embedding helpers and adapters for memory indexing."""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import cast

from flow_res import Err, Ok, Result
from google import genai
from google.genai import types

from app.contracts.ports.embedding_service import (
    EmbeddingServiceError,
    IEmbeddingService,
)

_TERM_PATTERN = re.compile(r"[\w一-龯ぁ-んァ-ヶー]+", re.UNICODE)
_DEFAULT_DIMENSION = 16


class DeterministicEmbeddingService(IEmbeddingService):
    """Generate stable embeddings without a remote provider."""

    def __init__(self, dimension: int = 16) -> None:
        self._dimension = max(dimension, 1)

    async def embed_texts(
        self,
        texts: list[str],
    ) -> Result[list[list[float]], EmbeddingServiceError]:
        """Embed texts with a deterministic hash-based vector."""
        return Ok(
            [
                embed_text_deterministically(text, dimension=self._dimension)
                for text in texts
            ]
        )


class GeminiEmbeddingService(IEmbeddingService):
    """Generate embeddings using Gemini."""

    def __init__(
        self,
        *,
        model: str | None = None,
        output_dimensionality: int = 768,
    ) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        self._client = genai.Client(api_key=api_key) if api_key else None
        self._model = model or os.getenv(
            "GEMINI_EMBEDDING_MODEL",
            "gemini-embedding-001",
        )
        self._output_dimensionality = output_dimensionality

    async def embed_texts(
        self,
        texts: list[str],
    ) -> Result[list[list[float]], EmbeddingServiceError]:
        """Generate embeddings for a batch of texts."""

        if self._client is None:
            return Err(EmbeddingServiceError("Gemini API key not configured."))

        try:
            response = await self._client.aio.models.embed_content(
                model=self._model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type="SEMANTIC_SIMILARITY",
                    output_dimensionality=self._output_dimensionality,
                ),
            )
            embeddings = [
                list(cast(list[float], embedding.values))
                for embedding in (response.embeddings or [])
            ]
            return Ok(embeddings)
        except Exception as exc:
            return Err(EmbeddingServiceError(f"Gemini embedding error: {exc}"))


def embed_text_deterministically(
    text: str,
    *,
    dimension: int = _DEFAULT_DIMENSION,
) -> list[float]:
    """Return a deterministic embedding for the supplied text."""

    return _embed_text(text, dimension=dimension)


def embed_texts_deterministically(
    texts: list[str],
    *,
    dimension: int = _DEFAULT_DIMENSION,
) -> list[list[float]]:
    """Return deterministic embeddings for a batch of texts."""

    return [embed_text_deterministically(text, dimension=dimension) for text in texts]


def _embed_text(text: str, *, dimension: int) -> list[float]:
    terms = _TERM_PATTERN.findall(text.lower())
    if not terms:
        return [0.0] * dimension

    vector = [0.0] * dimension
    for term in terms:
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        for index in range(dimension):
            vector[index] += digest[index % len(digest)] / 255.0

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0] * dimension
    return [round(value / norm, 6) for value in vector]
