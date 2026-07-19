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
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.memory_semantic_extraction import (
    LongTermMemoryChatLog,
    MemoryEntityPatch,
    MemoryProfilePatch,
    MemorySectionSummary,
    MemorySemanticExtractionRequest,
    MemoryTimelineSectionPatch,
)
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import AIServiceError, IAIService
from app.domain.queries.raw_chat_log_query import LongTermMemorySourceItem
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.services.memory_consolidation import (
    MemoryConsolidationService,
    _validate_section_source_chat_ids,
    _write_entity_patch,
    _write_profile_patch,
)
from app.infrastructure.services.memory_semantic_extraction import (
    MemorySemanticExtractionService,
)
from tests._relationship_fixture import relationship_definition


class _FakeAIService(IAIService):
    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
        tool_results: list[ToolResultContext] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        del prompt, history, system_instruction, tool_definitions, tool_results
        payload = {
            "sections": [
                {
                    "id": "u1-2026-05-18-work-progress",
                    "user_id": "u1",
                    "day": "2026-05-18",
                    "section_slug": "work-progress",
                    "title": "Work progress",
                    "source_chat_ids": ["raw-1", "raw-2"],
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
            "source_evaluations": [
                {"chat_id": "raw-1", "disposition": "used", "reason": "根拠"},
                {"chat_id": "raw-2", "disposition": "used", "reason": "根拠"},
            ],
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
        tool_results: list[ToolResultContext] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        self.last_prompt = prompt
        self.last_system_instruction = system_instruction
        return await super().generate_content(
            prompt,
            history,
            system_instruction,
            tool_definitions,
            tool_results,
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
        tool_results: list[ToolResultContext] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        del history, tool_definitions, tool_results
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
            "sections": [
                {
                    "id": "u1-2026-05-18-work-progress",
                    "user_id": "u1",
                    "day": "2026-05-18",
                    "section_slug": "work-progress",
                    "title": "Work progress",
                    "source_chat_ids": ["raw-1", "raw-2"],
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
            "source_evaluations": [
                {"chat_id": "raw-1", "disposition": "used", "reason": "根拠"},
                {"chat_id": "raw-2", "disposition": "used", "reason": "根拠"},
            ],
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
        tool_results: list[ToolResultContext] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        del history, tool_definitions, tool_results
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
    character=CharacterDefinition(character_id="jondue"),
    persona_context="\n".join(
        [
            "You are Jon Due, a calm host persona.",
            "Speak in natural English with a composed tone.",
            "Keep responses warm, clear, and attentive.",
        ]
    ),
    relationship=relationship_definition(),
)


def _section_patch(
    section_id: str,
    source_chat_ids: list[str],
) -> MemoryTimelineSectionPatch:
    return MemoryTimelineSectionPatch(
        id=section_id,
        user_id="u1",
        day="2026-05-18",
        section_slug=section_id,
        title=section_id,
        source_chat_ids=source_chat_ids,
        summary=MemorySectionSummary(
            topic="topic",
            self_feeling="feeling",
            other_feeling="other feeling",
            outcome="outcome",
        ),
        confidence=0.9,
    )


def test_section_source_chat_ids_must_reference_available_raw_logs() -> None:
    with pytest.raises(ValueError, match="unknown source_chat_ids"):
        _validate_section_source_chat_ids(
            [_section_patch("section-one", ["raw-unknown"])],
            available_source_chat_ids=["raw-1"],
        )


def test_source_chat_id_must_belong_to_exactly_one_section() -> None:
    with pytest.raises(ValueError, match="exactly one section"):
        _validate_section_source_chat_ids(
            [
                _section_patch("section-one", ["raw-1"]),
                _section_patch("section-two", ["raw-1"]),
            ],
            available_source_chat_ids=["raw-1"],
        )


class _RelationshipAIService(IAIService):
    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
        tool_results: list[ToolResultContext] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        del prompt, history, system_instruction, tool_definitions, tool_results
        payload = {
            "sections": [],
            "entity_patches": [],
            "profile_patch": None,
            "evidence": {
                "notes": ["User returned and continued a respectful topic"],
            },
            "source_evaluations": [
                {"chat_id": "raw-1", "disposition": "used", "reason": "根拠"}
            ],
            "relationship_signals": [
                {
                    "kind": "positive",
                    "confidence": 0.91,
                    "reason": "丁寧な会話を継続した",
                    "source_chat_ids": ["raw-1"],
                    "observed_at": "2026-05-18T10:00:00Z",
                }
            ],
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
    assert result.value.sections[0].source_chat_ids == ["raw-1", "raw-2"]
    assert result.value.sections[0].summary.topic == "Team planning"
    assert result.value.sections[0].summary.self_feeling == "Focused and steady."
    assert result.value.sections[0].summary.outcome == "The memory update was agreed."


@pytest.mark.anyio
async def test_memory_semantic_extraction_service_system_instruction_is_json_only() -> (
    None
):
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
    assert (
        "JSON の文字列値は自然な日本語にしてください"
        in recording_ai.last_system_instruction
    )
    assert (
        "出力文体は自然な日本語にしてください"
        not in recording_ai.last_system_instruction
    )


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
            LongTermMemoryChatLog(
                id="raw-1",
                user_id="u1",
                character_id="shirasagi-reina",
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
        "Memory semantic extraction context:" in record.message
        for record in caplog.records
    )
    assert any(
        "raw_logs=id=raw-1,role=user,type=DISCORD" in record.message
        for record in caplog.records
    )
    assert any(
        "existing_profile_summary=Profile summary for context" in record.message
        for record in caplog.records
    )
    assert any(
        "existing_entity_labels=project-x | relationship:jondue" in record.message
        for record in caplog.records
    )
    assert any(
        "existing_timeline_summaries=Timeline summary one" in record.message
        for record in caplog.records
    )
    assert any(
        "Memory semantic extraction result:" in record.message
        for record in caplog.records
    )
    assert any(
        "sections=work-progress:Work progress" in record.message
        for record in caplog.records
    )
    assert any(
        "evidence_notes=User mentioned project-x" in record.message
        for record in caplog.records
    )


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

    with caplog.at_level(
        logging.INFO, logger="app.infrastructure.services.memory_semantic_extraction"
    ):
        result = await service.extract_memory_updates(request)

    assert is_ok(result)
    assert result.value.sections[0].summary.topic == "Team planning"
    assert len(ai_service.prompts) == 2
    assert ai_service.system_instructions[0] is not None
    assert ai_service.system_instructions[1] is not None
    assert "JSON" in ai_service.system_instructions[1]
    assert any("non-JSON output" in record.message for record in caplog.records)
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

    with caplog.at_level(
        logging.WARNING, logger="app.infrastructure.services.memory_semantic_extraction"
    ):
        result = await service.extract_memory_updates(request)

    assert not is_ok(result)
    assert len(ai_service.prompts) == 2
    assert any("non-JSON output" in record.message for record in caplog.records)
    assert any("failed after 2 attempts" in record.message for record in caplog.records)


@pytest.mark.anyio
async def test_memory_consolidation_includes_recent_timeline_summaries_in_prompt(
    tmp_path: Path,
) -> None:
    """Memory organization should include recent timeline summaries as context."""

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
        LongTermMemorySourceItem(
            id="raw-1",
            character_id="shirasagi-reina",
            user_id="u1",
            role="user",
            chat_type=ChatType.DISCORD,
            message_content={
                "type": "TEXT",
                "payload": {"texts": ["Planning project-x."]},
            },
            created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        ),
        LongTermMemorySourceItem(
            id="raw-2",
            character_id="shirasagi-reina",
            user_id="u1",
            role="assistant",
            chat_type=ChatType.LINE,
            message_content={
                "type": "TEXT",
                "payload": {"texts": ["Captured memory update."]},
            },
            created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
        ),
    ]

    recording_ai = _RecordingAIService()
    service = MemoryConsolidationService(
        store=store,
        semantic_extraction_service=MemorySemanticExtractionService(
            recording_ai,
            _FakeAgentProfileService(),
        ),
        agent_profile_service=_FakeAgentProfileService(),
    )

    consolidation_result = await service.consolidate_chat_logs(
        user_id="u1",
        day=datetime(2026, 5, 18).date(),
        raw_logs=raw_logs,
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )

    assert consolidation_result.episode_upserted_count == 1
    assert consolidation_result.evaluated_chat_ids == ("raw-1", "raw-2")
    assert recording_ai.last_prompt is not None
    assert '"source_chat_ids": ["raw-chat-id"]' in recording_ai.last_prompt
    assert "1 つの raw log id を複数の section" in recording_ai.last_prompt
    assert "既存の Timeline 要約:" in recording_ai.last_prompt
    assert "2026-05-17:" in recording_ai.last_prompt
    assert "Yesterday summary" in recording_ai.last_prompt
    assert "ラノベのタイトルや章タイトルのように" in recording_ai.last_prompt
    assert "8〜14 文字前後" in recording_ai.last_prompt
    assert '"relationship_signals"' in recording_ai.last_prompt
    assert "関係状態をEntityとして出力せず" in recording_ai.last_prompt


@pytest.mark.anyio
async def test_consolidate_conversation_history_uses_semantic_extraction_service(
    tmp_path: Path,
) -> None:
    """Memory organization should write from semantic extraction output."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    _write_entity(store, user_id="u1", entity_id="project-x")
    raw_logs = [
        LongTermMemorySourceItem(
            id="raw-1",
            character_id="shirasagi-reina",
            user_id="u1",
            role="user",
            chat_type=ChatType.DISCORD,
            message_content={
                "type": "TEXT",
                "payload": {"texts": ["Planning project-x."]},
            },
            created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        ),
        LongTermMemorySourceItem(
            id="raw-2",
            character_id="shirasagi-reina",
            user_id="u1",
            role="assistant",
            chat_type=ChatType.LINE,
            message_content={
                "type": "TEXT",
                "payload": {"texts": ["Captured memory update."]},
            },
            created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
        ),
    ]

    service = MemoryConsolidationService(
        store=store,
        semantic_extraction_service=MemorySemanticExtractionService(
            _FakeAIService(),
            _FakeAgentProfileService(),
        ),
        agent_profile_service=_FakeAgentProfileService(),
    )

    consolidation_result = await service.consolidate_chat_logs(
        user_id="u1",
        day=datetime(2026, 5, 18).date(),
        raw_logs=raw_logs,
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )

    work = store.read_document(
        store.iter_timeline_paths("u1")[0],
        expected_memory_type="timeline",
        expected_user_id="u1",
    )

    assert consolidation_result.episode_upserted_count == 1
    assert work.front_matter["summary_of"] == ["raw-1", "raw-2"]
    assert work.front_matter["source_chat_ids"] == ["raw-1", "raw-2"]
    assert "Team planning" in work.body
    assert "Source Chat IDs" not in work.body
    assert "Evidence" not in work.body


@pytest.mark.anyio
async def test_memory_consolidation_reuses_existing_section_for_same_raw_logs(
    tmp_path: Path,
) -> None:
    """A repeat organization run should not create a second section for the same raws."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    day = datetime(2026, 5, 18).date()
    _write_timeline_summary(
        store,
        user_id="u1",
        day=day,
        section_slug="existing-work-progress",
        title="Existing work progress",
        body_lines=["- 何について話した: Earlier summary"],
        source_chat_ids=["raw-1", "raw-2"],
    )
    raw_logs = [
        LongTermMemorySourceItem(
            id="raw-1",
            character_id="shirasagi-reina",
            user_id="u1",
            role="user",
            chat_type=ChatType.DISCORD,
            message_content={
                "type": "TEXT",
                "payload": {"texts": ["Discussed project progress."]},
            },
            created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        ),
        LongTermMemorySourceItem(
            id="raw-2",
            character_id="shirasagi-reina",
            user_id="u1",
            role="assistant",
            chat_type=ChatType.LINE,
            message_content={
                "type": "TEXT",
                "payload": {"texts": ["Captured memory update."]},
            },
            created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
        ),
    ]
    service = MemoryConsolidationService(
        store=store,
        semantic_extraction_service=MemorySemanticExtractionService(
            _FakeAIService(),
            _FakeAgentProfileService(),
        ),
        agent_profile_service=_FakeAgentProfileService(),
    )

    consolidation_result = await service.consolidate_chat_logs(
        user_id="u1",
        day=day,
        raw_logs=raw_logs,
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )

    existing_path = store.section_timeline_path(
        user_id="u1",
        day=day,
        section_slug="existing-work-progress",
    )
    new_path = store.section_timeline_path(
        user_id="u1",
        day=day,
        section_slug="work-progress",
    )
    existing = store.read_document(
        existing_path,
        expected_memory_type="timeline",
        expected_user_id="u1",
    )

    assert consolidation_result.episode_upserted_count == 1
    assert existing_path.exists()
    assert not new_path.exists()
    assert existing.front_matter["section_slug"] == "existing-work-progress"
    assert existing.front_matter["source_chat_ids"] == ["raw-1", "raw-2"]
    assert "Team planning" in existing.body


@pytest.mark.anyio
async def test_memory_consolidation_returns_relationship_signals_without_entity(
    tmp_path: Path,
) -> None:
    """Relationship signals should leave memory Entity persistence untouched."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    raw_logs = [
        LongTermMemorySourceItem(
            id="raw-1",
            character_id="shirasagi-reina",
            user_id="u1",
            role="user",
            chat_type=ChatType.DISCORD,
            message_content={
                "type": "TEXT",
                "payload": {"texts": ["今日も少し話したくて来た。"]},
            },
            created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        )
    ]
    service = MemoryConsolidationService(
        store=store,
        semantic_extraction_service=MemorySemanticExtractionService(
            _RelationshipAIService(),
            _FakeAgentProfileService(),
        ),
        agent_profile_service=_FakeAgentProfileService(),
    )

    consolidation_result = await service.consolidate_chat_logs(
        user_id="u1",
        day=datetime(2026, 5, 18).date(),
        raw_logs=raw_logs,
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )

    assert consolidation_result.episode_upserted_count == 0
    assert consolidation_result.entity_upserted_count == 0
    assert len(consolidation_result.relationship_signals) == 1
    assert consolidation_result.relationship_signals[0].kind == "positive"
    assert not store.iter_entity_paths("u1")


def test_profile_correction_replaces_obsolete_preferences(tmp_path: Path) -> None:
    store = FilesystemMemoryStore(tmp_path / "memory")
    store.write_document(
        store.user_profile_path("u1"),
        front_matter={
            "schema_version": 1,
            "memory_type": "profile",
            "id": "profile:u1",
            "user_id": "u1",
            "profile_scope": "user",
            "summary": "食の好み",
            "traits": [],
            "preferences": ["ぶどうが好き"],
            "created_at": "2026-05-17T00:00:00+00:00",
            "updated_at": "2026-05-17T00:00:00+00:00",
        },
        body="# u1",
    )

    _write_profile_patch(
        store,
        user_id="u1",
        profile_patch=MemoryProfilePatch(
            user_id="u1",
            summary="食の好み",
            preferences=["ぶどうが嫌い"],
            confidence=0.95,
            source_chat_ids=["raw-1"],
            observed_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
            update_mode="replace",
        ),
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )

    profile = store.read_document(
        store.user_profile_path("u1"),
        expected_memory_type="profile",
        expected_user_id="u1",
    )
    assert profile.front_matter["preferences"] == ["ぶどうが嫌い"]
    assert "ぶどうが好き" not in profile.body


def test_entity_transition_retains_previous_temporal_value(tmp_path: Path) -> None:
    store = FilesystemMemoryStore(tmp_path / "memory")
    _write_entity(store, user_id="u1", entity_id="employment")
    entity_path = store.entity_path("u1", "employment")
    existing = store.read_document(entity_path)
    existing_front_matter = dict(existing.front_matter)
    existing_front_matter["properties"] = {"company": "旧会社"}
    existing_front_matter["source_chat_ids"] = ["raw-old"]
    store.write_document(
        entity_path,
        front_matter=existing_front_matter,
        body=existing.body,
    )

    _write_entity_patch(
        store,
        entity_patch=MemoryEntityPatch(
            id="employment",
            user_id="u1",
            label="勤務先",
            entity_type="employment",
            status="active",
            properties={"company": "新会社"},
            confidence=0.9,
            source_chat_ids=["raw-new"],
            observed_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
            update_mode="transition",
        ),
        source_chat_ids=["raw-new"],
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )

    entity = store.read_document(entity_path)
    assert cast(dict[str, object], entity.front_matter["properties"])["company"] == (
        "新会社"
    )
    history = cast(list[dict[str, object]], entity.front_matter["property_history"])
    assert history[0]["value"] == "旧会社"
    assert history[0]["source_chat_ids"] == ["raw-old"]


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


def _write_timeline_summary(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
    day: date,
    section_slug: str,
    title: str,
    body_lines: list[str],
    source_chat_ids: list[str] | None = None,
) -> None:
    resolved_source_chat_ids = source_chat_ids or []
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
            "summary_of": resolved_source_chat_ids,
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
            "source_chat_ids": resolved_source_chat_ids,
            "extraction_confidence": 1.0,
        },
        body="\n".join(["# " + title, "", *body_lines]),
    )
