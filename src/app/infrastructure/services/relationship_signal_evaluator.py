"""LLM-backed relationship signal classification adapter."""

from __future__ import annotations

import json

from flow_res import Err, Ok, Result, is_err
from pydantic import ValidationError

from app.contracts.messages.relationship import (
    RelationshipSignalCandidate,
    RelationshipSignalEvaluationRequest,
)
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.relationship import (
    IRelationshipSignalEvaluator,
    RelationshipSignalEvaluationError,
)


class LLMRelationshipSignalEvaluator(IRelationshipSignalEvaluator):
    """Classify relationship changes without choosing character behavior."""

    def __init__(self, ai_service: IAIService) -> None:
        self._ai_service = ai_service

    async def evaluate(
        self,
        request: RelationshipSignalEvaluationRequest,
    ) -> Result[RelationshipSignalCandidate, RelationshipSignalEvaluationError]:
        generated = await self._ai_service.generate_content(
            _build_prompt(request),
            [],
            system_instruction=(
                "Classify only the user's relationship signal. "
                "Do not choose character behavior and return one JSON object."
            ),
        )
        if is_err(generated):
            return Err(RelationshipSignalEvaluationError(generated.error.message))
        try:
            raw_text = "\n".join(generated.value.contents).strip()
            payload = json.loads(raw_text)
            candidate = RelationshipSignalCandidate.model_validate(payload)
            return Ok(
                candidate.model_copy(
                    update={
                        "source_chat_ids": list(request.source_chat_ids),
                        "observed_at": request.observed_at,
                    }
                )
            )
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            return Err(RelationshipSignalEvaluationError(str(exc)))


def _build_prompt(request: RelationshipSignalEvaluationRequest) -> str:
    return "\n".join(
        (
            "Classify whether this interaction clearly changes affection.",
            "Ordinary conversation is neutral. Do not reward message length or frequency.",
            "Use positive for clear trust, care, honest disclosure, or repair.",
            "Use negative for rejection, broken trust, hostility, or boundary violations.",
            "Use strong variants only for explicit, consequential evidence.",
            'Return exactly: {"kind": "strong_negative|negative|neutral|positive|strong_positive", "confidence": 0.0, "reason": "short reason", "source_chat_ids": []}',
            f"mode: {request.mode}",
            "conversation:",
            request.conversation_text,
        )
    )
