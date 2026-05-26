"""Gemini service implementation."""

import os
from typing import Any, cast

from flow_res import Err, Ok, Result
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.ports.ai_service import (
    AIServiceError,
    IAIService,
)
from app.domain.aggregates.chat import Chat


def _parse_generated_content(payload: Any) -> GeneratedContent:
    """Parse structured Gemini output into the DTO."""
    if isinstance(payload, str):
        return GeneratedContent.model_validate_json(payload)
    return GeneratedContent.model_validate(payload)


class GeminiService(IAIService):
    """Implementation using Google Gemini."""

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        self._client = genai.Client(api_key=api_key) if api_key else None

    async def generate_content(
        self,
        prompt: str,
        history: list[Chat],
        system_instruction: str | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Generate structured content with Gemini."""
        if self._client is None:
            return Err(AIServiceError("Gemini API key not configured."))

        try:
            messages = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part(text=chat.message_content.payload.get("text", ""))
                    ],
                )
                for chat in history
            ]
            config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                max_output_tokens=2048,
                response_mime_type="application/json",
                response_json_schema=GeneratedContent.model_json_schema(),
            )
            if system_instruction is not None:
                config.system_instruction = system_instruction

            response = await self._client.aio.models.generate_content(
                model="gemini-3-flash-preview",
                contents=cast(
                    list[types.ContentOrDict],
                    messages
                    + [
                        types.Content(
                            role="user",
                            parts=[types.Part(text=prompt)],
                        )
                    ],
                ),
                config=config,
            )
            if response.parsed is not None:
                return Ok(_parse_generated_content(response.parsed))
            if response.text is None:
                return Err(AIServiceError("No content generated."))
            try:
                return Ok(_parse_generated_content(response.text))
            except ValidationError as e:
                return Err(AIServiceError(f"Invalid Gemini structured output: {e}"))
        except Exception as e:
            return Err(AIServiceError(f"Gemini API Error: {e}"))
