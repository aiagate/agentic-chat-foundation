"""Live scenario tests for memory semantic extraction."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime

import pytest
from flow_res import is_err

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.character_definition import CharacterDefinition
from app.contracts.messages.memory_context import MemoryProfile
from app.contracts.messages.memory_semantic_extraction import (
    MemorySemanticExtractionRequest,
    MemorySleepChatLog,
)
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import IAIService
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.services.gemini_service import GeminiService
from app.infrastructure.services.gpt_service import GptService
from app.infrastructure.services.memory_semantic_extraction import (
    MemorySemanticExtractionService,
)

pytestmark = pytest.mark.scenario

_SECTION_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class _ScenarioAgentProfileService(IAgentProfileService):
    def ensure_agent_profile_bundle(self) -> None:
        return None

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        return AgentProfileBundle(
            profile=MemoryProfile(
                user_id="ai",
                display_name="テストエージェント",
                summary="テスト用の人格。",
                traits=["寡黙"],
                preferences=["静かな場所"],
            ),
            character=CharacterDefinition(
                character_id="test-agent",
                display_name="テストエージェント",
                relationship_entity_id="relationship:test-agent",
                relationship_entity_label="テストエージェントとの関係",
            ),
            persona_context="Persona Contract:\n- test persona",
            communication_style=("日本語で自然に話す",),
            known_constraints=("AI と名乗らない",),
            atmosphere=("静かな夜",),
            behavior=("落ち着いた敬語を保つ。",),
            relationship_entity_id="relationship:test-agent",
            relationship_entity_label="テストエージェントとの関係",
            relationship_entity_type="relationship",
            relationship_tag="agent-growth",
            relationship=("最小限の自己開示",),
            fallback=("季節感のある料理を選ぶ",),
            memory_reading_rules=("Scenario bundle is read from memory files.",),
        )


@pytest.mark.anyio
async def test_live_ai_provider_extracts_memory_sections() -> None:
    """The live AI provider should return parseable memory extraction output."""

    ai_service = _build_live_ai_service()
    service = MemorySemanticExtractionService(
        ai_service,
        _ScenarioAgentProfileService(),
    )
    request = MemorySemanticExtractionRequest(
        user_id="u1",
        day="2026-05-18",
        raw_logs=[
            MemorySleepChatLog(
                id="raw-1",
                user_id="u1",
                role="user",
                chat_type=ChatType.LINE,
                content="明日の新幹線に乗る前に、お風呂と荷物の準備をどう進めるか相談したい。",
                occurred_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
            ),
            MemorySleepChatLog(
                id="raw-2",
                user_id="u1",
                role="assistant",
                chat_type=ChatType.LINE,
                content="まずお風呂に入ってから、充電器とお土産をまとめる流れがよさそう。",
                occurred_at=datetime(2026, 5, 18, 9, 5, tzinfo=UTC),
            ),
        ],
        existing_profile_summary="",
        existing_entity_labels=[],
        existing_timeline_summaries=[],
    )

    result = await service.extract_memory_updates(request)

    if is_err(result):
        pytest.fail(f"live provider returned an error: {result.error}")
    extraction = result.value
    assert extraction.sections, "live provider returned no extracted sections"

    section = extraction.sections[0]
    assert section.user_id == "u1"
    assert section.day == "2026-05-18"
    assert section.title.strip()
    assert 2 <= len(section.title.strip()) <= 32
    assert _SECTION_SLUG_PATTERN.fullmatch(section.section_slug) is not None
    assert section.summary.topic.strip()
    assert section.summary.self_feeling.strip()
    assert section.summary.other_feeling.strip()
    assert section.summary.outcome.strip()
    assert 0.0 <= section.confidence <= 1.0


def _build_live_ai_service() -> IAIService:
    provider = os.getenv("LIVE_AI_PROVIDER", "auto").strip().lower()
    if provider not in {"auto", "gemini", "openai"}:
        raise ValueError("LIVE_AI_PROVIDER must be one of: auto, gemini, openai")

    if provider in {"auto", "gemini"} and os.getenv("GEMINI_API_KEY"):
        return GeminiService()
    if provider in {"auto", "openai"} and os.getenv("OPENAI_API_KEY"):
        return GptService()

    pytest.skip(
        "Set RUN_SCENARIO_TESTS=1 and configure GEMINI_API_KEY or OPENAI_API_KEY "
        "to run live AI scenario tests."
    )
