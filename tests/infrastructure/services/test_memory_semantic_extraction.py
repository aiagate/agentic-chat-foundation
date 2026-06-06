"""Tests for memory semantic extraction."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest
from flow_res import Ok, Result, is_ok

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.character_definition import CharacterDefinition
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.memory_context import MemoryProfile
from app.contracts.messages.memory_semantic_extraction import (
    MemorySemanticExtractionRequest,
    MemorySleepChatLog,
)
from app.contracts.messages.relationship_growth import MAX_DAILY_SCORE_INCREASE
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import AIServiceError, IAIService
from app.domain.queries.raw_chat_log_query import MemorySleepSourceItem
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.services.memory_consolidation import MemoryConsolidationService
from app.infrastructure.services.memory_semantic_extraction import (
    MemorySemanticExtractionService,
)


class _FakeAIService(IAIService):
    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        del prompt, history, system_instruction, tool_definitions
        payload = {
            "sections": [
                {
                    "id": "u1-2026-05-18-work-progress",
                    "user_id": "u1",
                    "day": "2026-05-18",
                    "section_slug": "work-progress",
                    "title": "Work progress",
                    "summary": {
                        "topic": "Team planning",
                        "self_feeling": "Focused and steady.",
                        "other_feeling": "Collaborative and supportive.",
                        "outcome": "The memory update was agreed.",
                    },
                    "entity_ids": ["project-x"],
                    "confidence": 0.92,
                }
            ],
            "timeline_patch": None,
            "entity_patches": [],
            "profile_patch": None,
            "evidence": {
                "notes": ["User mentioned project-x"],
            },
        }
        return Ok(GeneratedContent(contents=[json.dumps(payload)]))


class _RecordingAIService(_FakeAIService):
    def __init__(self) -> None:
        self.last_prompt: str | None = None
        self.last_system_instruction: str | None = None

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        self.last_prompt = prompt
        self.last_system_instruction = system_instruction
        return await super().generate_content(
            prompt,
            history,
            system_instruction,
            tool_definitions,
        )


class _RetryingAIService(IAIService):
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.system_instructions: list[str | None] = []

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        del history, tool_definitions
        self.prompts.append(prompt)
        self.system_instructions.append(system_instruction)

        if len(self.prompts) == 1:
            return Ok(
                GeneratedContent(
                    contents=[
                        "承知いたしました。要点を整理してお伝えします。",
                    ]
                )
            )

        payload = {
            "timeline_patch": None,
            "sections": [
                {
                    "id": "u1-2026-05-18-work-progress",
                    "user_id": "u1",
                    "day": "2026-05-18",
                    "section_slug": "work-progress",
                    "title": "Work progress",
                    "summary": {
                        "topic": "Team planning",
                        "self_feeling": "Focused and steady.",
                        "other_feeling": "Collaborative and supportive.",
                        "outcome": "The memory update was agreed.",
                    },
                    "entity_ids": ["project-x"],
                    "confidence": 0.92,
                }
            ],
            "entity_patches": [],
            "profile_patch": None,
            "evidence": {
                "notes": ["User mentioned project-x"],
            },
        }
        return Ok(GeneratedContent(contents=[json.dumps(payload, ensure_ascii=False)]))


class _AlwaysInvalidAIService(IAIService):
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.system_instructions: list[str | None] = []

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        del history, tool_definitions
        self.prompts.append(prompt)
        self.system_instructions.append(system_instruction)
        return Ok(
            GeneratedContent(
                contents=[
                    "承知いたしました。要点を整理してお伝えします。",
                ]
            )
        )


class _FakeAgentProfileService(IAgentProfileService):
    def ensure_agent_profile_bundle(self) -> None:
        return None

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        return AGENT_PROFILE_BUNDLE


AGENT_PROFILE_BUNDLE = AgentProfileBundle(
    profile=MemoryProfile(
        user_id="ai",
        display_name="Jon Due",
        summary=(
            "A calm host persona who is thoughtful, practical, and quietly warm. "
            "He keeps his responses measured and attentive."
        ),
        traits=[
            "calm",
            "rational",
            "courteous",
            "thoughtful",
            "measured",
        ],
        preferences=[
            "city lights",
            "quiet places",
            "clear answers",
        ],
    ),
    character=CharacterDefinition(
        character_id="jondue",
        display_name="Jon Due",
        relationship_entity_id="relationship:jondue",
        relationship_entity_label="Relationship with Jon Due",
    ),
    persona_context="\n".join(
        [
            "You are Jon Due, a calm host persona.",
            "Speak in natural English with a composed tone.",
            "Keep responses warm, clear, and attentive.",
        ]
    ),
    communication_style=("Speak naturally in English",),
    known_constraints=("Do not mention being an AI",),
    atmosphere=("A quiet evening with city lights in the distance.",),
    behavior=("Maintain a composed, respectful tone.",),
    relationship_entity_id="relationship:jondue",
    relationship_entity_label="Relationship with Jon Due",
    relationship_entity_type="relationship",
    relationship_tag="agent-growth",
    relationship=(
        "Relationship growth is user-scoped and must be read from the relationship Entity, not from the global agent profile.",
        "Use the current stage to adjust warmth, continuity, and self-disclosure subtly.",
        "Never use relationship growth to create dependency, jealousy, exclusivity, or pressure.",
    ),
    fallback=(
        "If preferences are unclear, choose something seasonal and quiet.",
        "Show consideration without becoming overly familiar.",
    ),
    memory_reading_rules=(
        "This file holds the long-term recap that complements the AGENTS, SOUL, and PERSONAL files.",
    ),
)


class _RelationshipAIService(IAIService):
    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        del prompt, history, system_instruction, tool_definitions
        payload = {
            "sections": [],
            "timeline_patch": None,
            "entity_patches": [
                {
                    "id": AGENT_PROFILE_BUNDLE.relationship_entity_id,
                    "user_id": "u1",
                    "label": AGENT_PROFILE_BUNDLE.relationship_entity_label,
                    "entity_type": AGENT_PROFILE_BUNDLE.relationship_entity_type,
                    "status": "active",
                    "aliases": [],
                    "attributes": {},
                    "properties": {
                        "trust_score": 80,
                        "warmth_score": 80,
                        "evidence_count": 2,
                        "recent_signal": "There was a polite follow-up conversation.",
                    },
                    "missing_attributes": [],
                    "confidence": 0.91,
                }
            ],
            "profile_patch": None,
            "evidence": {
                "notes": ["User returned and continued a respectful topic"],
            },
        }
        return Ok(GeneratedContent(contents=[json.dumps(payload, ensure_ascii=False)]))


@pytest.mark.anyio
async def test_memory_semantic_extraction_service_parses_structured_json() -> None:
    """LLM semantic extraction should round-trip validated JSON output."""

    service = MemorySemanticExtractionService(
        _FakeAIService(),
        _FakeAgentProfileService(),
    )
    request = MemorySemanticExtractionRequest(
        user_id="u1",
        day="2026-05-18",
        raw_logs=[],
    )

    result = await service.extract_memory_updates(request)

    assert is_ok(result)
    assert result.value.sections[0].summary.topic == "Team planning"
    assert result.value.sections[0].summary.self_feeling == "Focused and steady."
    assert result.value.sections[0].summary.outcome == "The memory update was agreed."


@pytest.mark.anyio
async def test_memory_semantic_extraction_service_system_instruction_is_json_only() -> None:
    """The system instruction should not ask for prose outside the JSON payload."""

    recording_ai = _RecordingAIService()
    service = MemorySemanticExtractionService(
        recording_ai,
        _FakeAgentProfileService(),
    )
    request = MemorySemanticExtractionRequest(
        user_id="u1",
        day="2026-05-18",
        raw_logs=[],
    )

    await service.extract_memory_updates(request)

    assert recording_ai.last_system_instruction is not None
    assert "JSON の文字列値は自然な日本語にしてください" in recording_ai.last_system_instruction
    assert "出力文体は自然な日本語にしてください" not in recording_ai.last_system_instruction


@pytest.mark.anyio
async def test_memory_semantic_extraction_service_logs_references_and_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The extraction service should log both references and the resulting patches."""

    ai_service = _FakeAIService()
    service = MemorySemanticExtractionService(
        ai_service,
        _FakeAgentProfileService(),
    )
    request = MemorySemanticExtractionRequest(
        user_id="u1",
        day="2026-05-18",
        raw_logs=[
            MemorySleepChatLog(
                id="raw-1",
                user_id="u1",
                role="user",
                chat_type=ChatType.DISCORD,
                content="Planning project-x and checking next steps.",
                occurred_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
            )
        ],
        existing_profile_summary="Profile summary for context",
        existing_entity_labels=["project-x", "relationship:jondue"],
        existing_timeline_summaries=["Timeline summary one"],
    )

    with caplog.at_level(
        logging.INFO,
        logger="app.infrastructure.services.memory_semantic_extraction",
    ):
        result = await service.extract_memory_updates(request)

    assert is_ok(result)
    assert any(
        "Memory semantic extraction context:" in record.message for record in caplog.records
    )
    assert any("raw_logs=id=raw-1,role=user,type=DISCORD" in record.message for record in caplog.records)
    assert any("existing_profile_summary=Profile summary for context" in record.message for record in caplog.records)
    assert any("existing_entity_labels=project-x | relationship:jondue" in record.message for record in caplog.records)
    assert any("existing_timeline_summaries=Timeline summary one" in record.message for record in caplog.records)
    assert any(
        "Memory semantic extraction result:" in record.message for record in caplog.records
    )
    assert any("sections=work-progress:Work progress" in record.message for record in caplog.records)
    assert any("evidence_notes=User mentioned project-x" in record.message for record in caplog.records)


@pytest.mark.anyio
async def test_memory_semantic_extraction_service_retries_until_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Non-JSON output should trigger one correction retry and then parse."""

    ai_service = _RetryingAIService()
    service = MemorySemanticExtractionService(
        ai_service,
        _FakeAgentProfileService(),
    )
    request = MemorySemanticExtractionRequest(
        user_id="u1",
        day="2026-05-18",
        raw_logs=[],
    )

    with caplog.at_level(logging.INFO, logger="app.infrastructure.services.memory_semantic_extraction"):
        result = await service.extract_memory_updates(request)

    assert is_ok(result)
    assert result.value.sections[0].summary.topic == "Team planning"
    assert len(ai_service.prompts) == 2
    assert ai_service.system_instructions[0] is not None
    assert ai_service.system_instructions[1] is not None
    assert "JSON" in ai_service.system_instructions[1]
    assert any(
        "non-JSON output" in record.message for record in caplog.records
    )
    assert any(
        "succeeded after 2 attempt" in record.message for record in caplog.records
    )


@pytest.mark.anyio
async def test_memory_semantic_extraction_service_reports_failure_after_retry_exhausted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Persistent non-JSON output should surface a clear extraction error."""

    ai_service = _AlwaysInvalidAIService()
    service = MemorySemanticExtractionService(
        ai_service,
        _FakeAgentProfileService(),
    )
    request = MemorySemanticExtractionRequest(
        user_id="u1",
        day="2026-05-18",
        raw_logs=[],
    )

    with caplog.at_level(logging.WARNING, logger="app.infrastructure.services.memory_semantic_extraction"):
        result = await service.extract_memory_updates(request)

    assert not is_ok(result)
    assert len(ai_service.prompts) == 2
    assert any(
        "non-JSON output" in record.message for record in caplog.records
    )
    assert any(
        "failed after 2 attempts" in record.message for record in caplog.records
    )


@pytest.mark.anyio
async def test_memory_consolidation_includes_recent_timeline_summaries_in_prompt(
    tmp_path: Path,
) -> None:
    """Sleep orchestration should include recent timeline summaries as context."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    _write_timeline_summary(
        store,
        user_id="u1",
        day=datetime(2026, 5, 17).date(),
        section_slug="yesterday-summary",
        title="Yesterday summary",
        body_lines=[
            "- 何について話した: Planning project-x.",
            "- 自分がどう感じたか: Focused and steady.",
            "- 相手がどう感じていそうか: Collaborative.",
            "- 結果として残ったこと: The plan was confirmed.",
        ],
    )
    raw_logs = [
        MemorySleepSourceItem(
            id="raw-1",
            user_id="u1",
            role="user",
            chat_type=ChatType.DISCORD,
            message_content={"payload": {"text": "Planning project-x."}},
            created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        ),
        MemorySleepSourceItem(
            id="raw-2",
            user_id="u1",
            role="assistant",
            chat_type=ChatType.LINE,
            message_content={"payload": {"text": "Captured memory update."}},
            created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
        ),
    ]

    recording_ai = _RecordingAIService()
    service = MemoryConsolidationService(
        semantic_extraction_service=MemorySemanticExtractionService(
            recording_ai,
            _FakeAgentProfileService(),
        ),
        agent_profile_service=_FakeAgentProfileService(),
    )

    consolidated_count = await service.consolidate_chat_logs(
        store,
        user_id="u1",
        day=datetime(2026, 5, 18).date(),
        raw_logs=raw_logs,
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )

    assert consolidated_count == 1
    assert recording_ai.last_prompt is not None
    assert "既存の Timeline 要約:" in recording_ai.last_prompt
    assert "2026-05-17:" in recording_ai.last_prompt
    assert "Yesterday summary" in recording_ai.last_prompt
    assert "ラノベのタイトルや章タイトルのように" in recording_ai.last_prompt
    assert "8〜14 文字前後" in recording_ai.last_prompt
    assert AGENT_PROFILE_BUNDLE.relationship_entity_id in recording_ai.last_prompt
    assert "依存、嫉妬、独占欲、駆け引き" in recording_ai.last_prompt


@pytest.mark.anyio
async def test_run_memory_sleep_uses_semantic_extraction_service(
    tmp_path: Path,
) -> None:
    """Sleep orchestration should write memory from semantic extraction output."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    _write_entity(store, user_id="u1", entity_id="project-x")
    raw_logs = [
        MemorySleepSourceItem(
            id="raw-1",
            user_id="u1",
            role="user",
            chat_type=ChatType.DISCORD,
            message_content={"payload": {"text": "Planning project-x."}},
            created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        ),
        MemorySleepSourceItem(
            id="raw-2",
            user_id="u1",
            role="assistant",
            chat_type=ChatType.LINE,
            message_content={"payload": {"text": "Captured memory update."}},
            created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
        ),
    ]

    service = MemoryConsolidationService(
        semantic_extraction_service=MemorySemanticExtractionService(
            _FakeAIService(),
            _FakeAgentProfileService(),
        ),
        agent_profile_service=_FakeAgentProfileService(),
    )

    consolidated_count = await service.consolidate_chat_logs(
        store,
        user_id="u1",
        day=datetime(2026, 5, 18).date(),
        raw_logs=raw_logs,
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )

    work = store.read_document(
        store.section_timeline_path(
            user_id="u1",
            day=datetime(2026, 5, 18).date(),
            section_slug="work-progress",
        ),
        expected_memory_type="timeline",
        expected_user_id="u1",
    )

    assert consolidated_count == 1
    assert work.front_matter["summary_of"] == ["raw-1", "raw-2"]
    assert work.front_matter["source_chat_ids"] == ["raw-1", "raw-2"]
    assert "Team planning" in work.body
    assert "Source Chat IDs" not in work.body
    assert "Evidence" not in work.body


@pytest.mark.anyio
async def test_memory_consolidation_upserts_relationship_entity_with_clamped_growth(
    tmp_path: Path,
) -> None:
    """Relationship patches should persist as user-scoped Entity memory."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    _write_relationship_entity(store, user_id="u1", trust_score=8, warmth_score=4)
    raw_logs = [
        MemorySleepSourceItem(
            id="raw-1",
            user_id="u1",
            role="user",
            chat_type=ChatType.DISCORD,
            message_content={"payload": {"text": "今日も少し話したくて来た。"}},
            created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        )
    ]
    service = MemoryConsolidationService(
        semantic_extraction_service=MemorySemanticExtractionService(
            _RelationshipAIService(),
            _FakeAgentProfileService(),
        ),
        agent_profile_service=_FakeAgentProfileService(),
    )

    consolidated_count = await service.consolidate_chat_logs(
        store,
        user_id="u1",
        day=datetime(2026, 5, 18).date(),
        raw_logs=raw_logs,
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )

    relationship = store.read_document(
        store.entity_path("u1", AGENT_PROFILE_BUNDLE.relationship_entity_id),
        expected_memory_type="entity",
        expected_user_id="u1",
    )

    assert consolidated_count == 0
    assert (
        relationship.front_matter["entity_type"]
        == AGENT_PROFILE_BUNDLE.relationship_entity_type
    )
    properties = cast(dict[str, object], relationship.front_matter["properties"])
    assert properties["trust_score"] == 8 + MAX_DAILY_SCORE_INCREASE
    assert properties["warmth_score"] == 4 + MAX_DAILY_SCORE_INCREASE
    assert properties["stage"] == 1
    assert properties["stage_name"] == "acquaintance"
    assert properties["recent_signal"] == "There was a polite follow-up conversation."
    assert relationship.front_matter["source_chat_ids"] == ["raw-1"]
    assert "## Relationship Stage" in relationship.body


def _write_entity(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
    entity_id: str,
) -> None:
    store.write_document(
        store.entity_path(user_id, entity_id),
        front_matter={
            "schema_version": 1,
            "memory_type": "entity",
            "id": entity_id,
            "user_id": user_id,
            "label": "Project X",
            "entity_type": "project",
            "status": "active",
            "aliases": [],
            "properties": {},
            "attributes": {},
            "missing_attributes": [],
            "referenced_in": [],
            "created_at": "2026-05-18T00:00:00+00:00",
            "updated_at": "2026-05-18T00:00:00+00:00",
            "tags": [],
            "importance": 0.6,
            "confidence": 1.0,
            "pinned": False,
            "metadata": {},
        },
        body="# Project X",
    )


def _write_relationship_entity(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
    trust_score: int,
    warmth_score: int,
) -> None:
    store.write_document(
        store.entity_path(user_id, AGENT_PROFILE_BUNDLE.relationship_entity_id),
        front_matter={
            "schema_version": 1,
            "memory_type": "entity",
            "id": AGENT_PROFILE_BUNDLE.relationship_entity_id,
            "user_id": user_id,
            "label": AGENT_PROFILE_BUNDLE.relationship_entity_label,
            "entity_type": AGENT_PROFILE_BUNDLE.relationship_entity_type,
            "status": "active",
            "aliases": [],
            "properties": {
                "stage": 0,
                "stage_name": "first-time guest",
                "trust_score": trust_score,
                "warmth_score": warmth_score,
                "evidence_count": 1,
                "recent_signal": "初回の会話",
            },
            "attributes": {},
            "missing_attributes": [],
            "referenced_in": [],
            "source_chat_ids": [],
            "created_at": "2026-05-17T00:00:00+00:00",
            "updated_at": "2026-05-17T00:00:00+00:00",
            "tags": ["relationship", "agent-growth"],
            "importance": 0.75,
            "confidence": 1.0,
            "pinned": False,
            "metadata": {},
        },
        body="# Relationship with Jon Due",
    )


def _write_timeline_summary(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
    day: date,
    section_slug: str,
    title: str,
    body_lines: list[str],
) -> None:
    store.write_document(
        store.section_timeline_path(
            user_id=user_id,
            day=day,
            section_slug=section_slug,
        ),
        front_matter={
            "schema_version": 1,
            "memory_type": "timeline",
            "id": f"{user_id}-{day.isoformat()}-{section_slug}",
            "user_id": user_id,
            "timeline_type": "section_summary",
            "kind": "summary",
            "content": "\n".join(body_lines),
            "occurred_at": f"{day.isoformat()}T00:00:00+00:00",
            "source": "consolidation",
            "entity_ids": [],
            "summary_of": [],
            "section_slug": section_slug,
            "section_title": title,
            "consolidation_state": "complete",
            "retention_state": "active",
            "last_accessed_at": None,
            "access_count": 0,
            "decay_score": 1.0,
            "created_at": "2026-05-17T00:00:00+00:00",
            "updated_at": "2026-05-17T00:00:00+00:00",
            "tags": [],
            "importance": 0.6,
            "confidence": 1.0,
            "pinned": False,
            "metadata": {},
            "source_chat_ids": [],
            "extraction_confidence": 1.0,
        },
        body="\n".join(["# " + title, "", *body_lines]),
    )
