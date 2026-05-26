"""OpenAI GPT service implementation."""

import json
import os
from typing import Any, cast

from flow_res import Err, Ok, Result
from openai import AsyncOpenAI
from openai.types.responses import ResponseInputItemParam

from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.ports.ai_service import (
    AIServiceError,
    IAIService,
)
from app.domain.aggregates.chat import Chat


def _parse_generated_content(payload: Any) -> GeneratedContent:
    """Parse structured OpenAI output into the DTO."""
    if isinstance(payload, str):
        return GeneratedContent.model_validate_json(payload)
    return GeneratedContent.model_validate(payload)


class GptService(IAIService):
    """Implementation using OpenAI Responses API."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def generate_content(
        self,
        prompt: str,
        history: list[Chat],
        system_instruction: str | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        """Generate structured content with OpenAI."""
        if self._client is None:
            return Err(AIServiceError("OpenAI API key not configured."))

        try:
            input_messages = [
                {
                    "role": "user",
                    "content": chat.message_content.payload.get("text", ""),
                }
                for chat in history
            ]
            input_messages.append({"role": "user", "content": prompt})

            response = await self._client.responses.create(
                model="gpt-4o-mini",
                instructions=system_instruction or "You are a helpful assistant.",
                input=cast(list[ResponseInputItemParam], input_messages),
                store=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "generated_content",
                        "schema": GeneratedContent.model_json_schema(),
                        "strict": True,
                    }
                },
            )
            return Ok(_parse_generated_content(json.loads(response.output_text)))
        except Exception as e:
            return Err(AIServiceError(f"OpenAI API Error: {e}"))
