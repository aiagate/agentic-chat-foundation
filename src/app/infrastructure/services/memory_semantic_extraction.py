"""LLM-backed memory semantic extraction service."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from flow_res import Err, Ok, Result, is_err
from pydantic import ValidationError

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.memory_semantic_extraction import (
    LongTermMemoryChatLog,
    MemoryEntityPatch,
    MemorySemanticExtractionRequest,
    MemorySemanticExtractionResult,
    MemoryTimelineSectionPatch,
)
from app.contracts.messages.relationship_growth import MAX_DAILY_SCORE_INCREASE
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.memory_semantic_extraction import (
    IMemorySemanticExtractionService,
    MemorySemanticExtractionError,
)

logger = logging.getLogger(__name__)
_MAX_JSON_EXTRACTION_ATTEMPTS = 2


@dataclass(slots=True)
class MemorySemanticExtractionService(IMemorySemanticExtractionService):
    """LLM-backed semantic extraction service for long-term memory."""

    ai_service: IAIService
    agent_profile_service: IAgentProfileService

    async def extract_memory_updates(
        self,
        request: MemorySemanticExtractionRequest,
    ) -> Result[MemorySemanticExtractionResult, MemorySemanticExtractionError]:
        """Extract structured memory patches from raw chat logs."""

        profile_bundle = self.agent_profile_service.load_agent_profile_bundle()
        prompt = _build_prompt(request, profile_bundle=profile_bundle)
        base_system_instruction = (
            "あなたはチャットログから長期記憶を抽出するアシスタントです。 "
            "返答は JSON オブジェクト 1 個だけにしてください。 "
            "JSON は指定された memory schema に厳密に一致させてください。 "
            "証拠のない事実を作らないでください。 "
            "簡潔で、ユーザーに紐づき、長く残る情報を優先してください。 "
            "JSON の文字列値は自然な日本語にしてください。 "
            "英語の文字列は不正な出力です。"
        )
        system_instruction = base_system_instruction
        logger.info(
            "Memory semantic extraction context: user_id=%s day=%s raw_logs=%s existing_profile_summary=%s existing_entity_labels=%s existing_timeline_summaries=%s prompt_chars=%s system_instruction_chars=%s",
            request.user_id,
            request.day,
            _summarize_raw_logs(request.raw_logs),
            _summarize_text(request.existing_profile_summary),
            _summarize_text_list(request.existing_entity_labels),
            _summarize_text_list(request.existing_timeline_summaries),
            len(prompt),
            len(system_instruction),
        )
        for attempt in range(1, _MAX_JSON_EXTRACTION_ATTEMPTS + 1):
            history: list[ChatHistoryItem] = []
            ai_result = await self.ai_service.generate_content(
                prompt,
                history,
                system_instruction=system_instruction,
                tool_definitions=None,
            )
            if is_err(ai_result):
                return Err(MemorySemanticExtractionError(str(ai_result.error)))

            extraction_result = _parse_generated_content(ai_result.value)
            if extraction_result is not None:
                logger.info(
                    "Memory semantic extraction result: user_id=%s day=%s sections=%s timeline_patch=%s entity_patches=%s profile_patch=%s evidence_notes=%s",
                    request.user_id,
                    request.day,
                    _summarize_sections(extraction_result.sections),
                    "yes" if extraction_result.timeline_patch is not None else "no",
                    _summarize_entity_patches(extraction_result.entity_patches),
                    "yes" if extraction_result.profile_patch is not None else "no",
                    _summarize_text_list(extraction_result.evidence.notes),
                )
                if attempt > 1:
                    logger.info(
                        "Memory semantic extraction succeeded after %s attempts for user_id=%s day=%s",
                        attempt,
                        request.user_id,
                        request.day,
                    )
                return Ok(extraction_result)

            preview = _summarize_generated_content(ai_result.value)
            logger.warning(
                "Memory semantic extraction returned non-JSON output on attempt %s for user_id=%s day=%s: %s",
                attempt,
                request.user_id,
                request.day,
                preview,
            )
            system_instruction = _build_retry_system_instruction(
                base_system_instruction,
                preview,
            )

        logger.error(
            "Memory semantic extraction failed after %s attempts for user_id=%s day=%s",
            _MAX_JSON_EXTRACTION_ATTEMPTS,
            request.user_id,
            request.day,
        )
        return Err(
            MemorySemanticExtractionError(
                "AI service returned no valid JSON payload after 2 attempts."
            )
        )


def _build_prompt(
    request: MemorySemanticExtractionRequest,
    *,
    profile_bundle: AgentProfileBundle,
) -> str:
    lines = [
        "以下の raw chat logs から、その日を後から思い出せる長期記憶を抽出してください。",
        "1 つの section は、話題・状況・感情がまとまった 1 シーンに対応させてください。",
        "同じ話題が続いているならまとめ、話題や場面が切り替わるなら分けてください。",
        "分けすぎないでください。細かい往復ごとに分けるのではなく、意味のある会話のまとまりで切ってください。",
        "各 section には、次の 4 点を必ず含む構造化 summary を返してください。",
        "- 何について話したか",
        "- 自分がどう感じたか",
        "- 相手がどう感じていそうか",
        "- 結果として何が残ったか / 決定事項",
        "各 section の source_chat_ids には、その section の根拠となった raw log の id だけを返してください。",
        "source_chat_ids は Raw logs に実在する id だけを使い、1 つ以上指定してください。",
        "1 つの raw log id を複数の section に重複して割り当てないでください。",
        "返答は 1 つの JSON オブジェクトのみで、次のスキーマに厳密に一致させてください。",
        "{",
        '  "sections": [',
        "    {",
        '      "id": "string",',
        '      "user_id": "string",',
        '      "day": "YYYY-MM-DD",',
        '      "section_slug": "coffee-break",',
        '      "title": "日本語の短い見出し",',
        '      "source_chat_ids": ["raw-chat-id"],',
        '      "summary": {',
        '        "topic": "string",',
        '        "self_feeling": "string",',
        '        "other_feeling": "string",',
        '        "outcome": "string"',
        "      },",
        '      "entity_ids": ["string"],',
        '      "confidence": 0.0',
        "    }",
        "  ],",
        '  "timeline_patch": { ... } | null,',
        '  "entity_patches": [',
        "    {",
        '      "id": "string",',
        '      "user_id": "string",',
        '      "label": "string",',
        '      "entity_type": "project|object|person|concept|relationship|...",',
        '      "status": "active|unresolved|deprecated|merged|archived",',
        '      "aliases": ["string"],',
        '      "attributes": {},',
        '      "properties": {},',
        '      "missing_attributes": ["string"],',
        '      "confidence": 0.0',
        "    }",
        "  ],",
        '  "profile_patch": { ... } | null,',
        '  "evidence": { "notes": ["string"] }',
        "}",
        "トップレベルのキーは増やさないでください。",
        "section_slug は英小文字の kebab-case で、安定して再利用できる短い名前にしてください。",
        "title は日本語で、短く、人間が読みやすい章題っぽい見出しにしてください。",
        "ラノベのタイトルや章タイトルのように、情景や内容が一目で分かる短い表現にしてください。",
        "長い説明文ではなく、8〜14 文字前後の簡潔な表現を優先してください。",
        "抽象的すぎる『雑談』『会話』『やりとり』のようなタイトルは避けてください。",
        "一方で、冗長な説明や副詞の連ね過ぎも避けてください。",
        "例: 『旅行の準備』『お風呂前のひと息』『新幹線での旅支度』『忘れ物とホテル段取り』『帰宅後のごはん』",
        "JSON の title, summary, evidence の文字列値は日本語で自然にしてください。英語は使わないでください。",
        "出力全体は JSON オブジェクト 1 個のみで、説明文や挨拶は書かないでください。",
        '  例: {"title": "お風呂前のひと息", "summary": {"topic": "お風呂に入る前に荷物や明日の準備をどう進めるか話した", "self_feeling": "少し急いでいるが、段取りを整えたい", "other_feeling": "相手は落ち着かせながら、先に何をするかを一緒に考えている", "outcome": "まずお風呂に入ってから荷物を整える流れになった"}}',
        "",
        "関係性 Entity 抽出ルール:",
        (
            "- "
            f"{profile_bundle.relationship_entity_label} に明確な変化がある場合だけ、"
            f"id '{profile_bundle.relationship_entity_id}' の entity_patch を返してください。"
        ),
        (
            f"- label は '{profile_bundle.relationship_entity_label}'、entity_type は "
            f"'{profile_bundle.relationship_entity_type}' にしてください。"
        ),
        (
            "- 新規作成時の基準値は "
            f"trust={profile_bundle.relationship_defaults.trust_score:.0f}, "
            f"warmth={profile_bundle.relationship_defaults.warmth_score:.0f}, "
            f"stage={profile_bundle.relationship_defaults.stage} です。"
        ),
        "- properties には trust_score, warmth_score, evidence_count, recent_signal を入れます。",
        "- trust_score と warmth_score は 0〜100 の数値です。",
        f"- 1 日の上昇提案は最大 +{MAX_DAILY_SCORE_INCREASE:.0f} を目安にしてください。",
        "- 不快、拒否、距離を置く発言がある場合は上昇させないでください。",
        "- assistant 側の願望、演出、自己都合を関係性の根拠にしないでください。",
        "- 依存、嫉妬、独占欲、駆け引きを成長条件にしないでください。",
        "- 根拠が弱い場合、関係性 entity_patch は返さず entity_patches を空のままにしてください。",
        f"user_id: {request.user_id}",
        f"day: {request.day}",
        "",
        "既存のプロフィール要約:",
        request.existing_profile_summary or "(なし)",
        "",
        "既存の Entity ラベル:",
        ", ".join(request.existing_entity_labels) or "(なし)",
        "",
        "既存の Timeline 要約:",
        ", ".join(request.existing_timeline_summaries) or "(なし)",
        "",
        "各 section の summary は、次のような 4 行の箇条書きとしてまとめるつもりで考えてください。",
        "- 何について話した: ...",
        "- 自分がどう感じたか: ...",
        "- 相手がどう感じていそうか: ...",
        "- 結果として残ったこと: ...",
        "",
        "Raw logs:",
    ]
    for raw_log in request.raw_logs:
        lines.extend(
            [
                f"- id: {raw_log.id}",
                f"  user_id: {raw_log.user_id}",
                f"  role: {raw_log.role}",
                f"  chat_type: {raw_log.chat_type.value}",
                f"  occurred_at: {raw_log.occurred_at.isoformat()}",
                f"  content: {raw_log.content}",
            ]
        )
    return "\n".join(lines)


def _summarize_raw_logs(
    raw_logs: list[LongTermMemoryChatLog],
    *,
    max_items: int = 5,
    max_content_length: int = 80,
) -> str:
    if not raw_logs:
        return "(none)"

    summarized_logs = [
        _summarize_raw_log(raw_log, max_content_length=max_content_length)
        for raw_log in raw_logs[:max_items]
    ]
    if len(raw_logs) > max_items:
        summarized_logs.append(f"...(+{len(raw_logs) - max_items} more)")
    return " | ".join(summarized_logs)


def _summarize_raw_log(
    raw_log: LongTermMemoryChatLog,
    *,
    max_content_length: int = 80,
) -> str:
    content = _summarize_text(raw_log.content, max_length=max_content_length)
    return (
        f"id={raw_log.id},role={raw_log.role},type={raw_log.chat_type.value},"
        f"at={raw_log.occurred_at.isoformat()},content={content}"
    )


def _summarize_text(text: str | None, *, max_length: int = 120) -> str:
    if text is None:
        return "(none)"

    collapsed = " ".join(text.split())
    if not collapsed:
        return "(empty)"
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[: max_length - 3]}..."


def _summarize_text_list(
    values: list[str],
    *,
    max_items: int = 5,
    max_length: int = 80,
) -> str:
    if not values:
        return "(none)"

    summarized_values = [
        _summarize_text(value, max_length=max_length) for value in values[:max_items]
    ]
    if len(values) > max_items:
        summarized_values.append(f"...(+{len(values) - max_items} more)")
    return " | ".join(summarized_values)


def _summarize_sections(
    sections: list[MemoryTimelineSectionPatch],
) -> str:
    if not sections:
        return "(none)"

    summarized_sections = [
        _summarize_text(f"{section.section_slug}:{section.title}", max_length=80)
        for section in sections[:5]
    ]
    if len(sections) > 5:
        summarized_sections.append(f"...(+{len(sections) - 5} more)")
    return " | ".join(summarized_sections)


def _summarize_entity_patches(
    entity_patches: list[MemoryEntityPatch],
) -> str:
    if not entity_patches:
        return "(none)"

    summarized_entity_patches = [
        _summarize_text(
            f"{entity_patch.id}:{entity_patch.label}:{entity_patch.status}",
            max_length=80,
        )
        for entity_patch in entity_patches[:5]
    ]
    if len(entity_patches) > 5:
        summarized_entity_patches.append(f"...(+{len(entity_patches) - 5} more)")
    return " | ".join(summarized_entity_patches)


def _parse_generated_content(
    generated_content: GeneratedContent,
) -> MemorySemanticExtractionResult | None:
    for payload in _generated_content_candidates(generated_content):
        try:
            return MemorySemanticExtractionResult.model_validate_json(payload)
        except ValidationError:
            continue
    return None


def _generated_content_candidates(
    generated_content: GeneratedContent,
) -> list[str]:
    candidates: list[str] = []
    for payload in generated_content.contents:
        stripped = payload.strip()
        if not stripped:
            continue
        candidates.append(stripped)
        fenced = _strip_json_fences(stripped)
        if fenced not in candidates:
            candidates.append(fenced)
        embedded = _extract_embedded_json_object(stripped)
        if embedded is not None and embedded not in candidates:
            candidates.append(embedded)
    return candidates


def _strip_json_fences(payload: str) -> str:
    """Extract a JSON payload from a fenced code block if present."""

    stripped = payload.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            body = "\n".join(lines[1:-1]).strip()
            if body:
                return body
    return stripped


def _extract_embedded_json_object(payload: str) -> str | None:
    """Extract the first JSON object substring from free-form output."""

    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return payload[start : end + 1].strip()


def _summarize_generated_content(
    generated_content: GeneratedContent,
    *,
    max_length: int = 240,
) -> str:
    """Return a short preview for log messages."""

    preview = " | ".join(
        content.strip() for content in generated_content.contents if content.strip()
    )
    if not preview:
        return "(empty)"
    if len(preview) <= max_length:
        return preview
    return f"{preview[: max_length - 3]}..."


def _build_retry_system_instruction(
    base_system_instruction: str,
    invalid_preview: str,
) -> str:
    """Tighten instructions after a non-JSON response."""

    correction = (
        "前回の返答は JSON ではありませんでした。"
        " 返答は JSON オブジェクト 1 個だけにしてください。"
        " 説明文、挨拶、前置き、箇条書きは不要です。"
        " JSON 以外の文字は出力しないでください。"
    )
    if invalid_preview != "(empty)":
        correction = f"{correction} 前回の出力の抜粋: {invalid_preview}"
    return "\n\n".join([base_system_instruction, correction])
