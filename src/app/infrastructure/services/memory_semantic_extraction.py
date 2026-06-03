"""LLM-backed memory semantic extraction service."""

from __future__ import annotations

from dataclasses import dataclass

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.memory_semantic_extraction import (
    MemorySemanticExtractionRequest,
    MemorySemanticExtractionResult,
)
from app.contracts.messages.relationship_growth import MAX_DAILY_SCORE_INCREASE
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.memory_semantic_extraction import (
    IMemorySemanticExtractionService,
    MemorySemanticExtractionError,
)


@dataclass(slots=True)
class MemorySemanticExtractionService(IMemorySemanticExtractionService):
    """LLM-backed semantic extraction service for memory sleep."""

    ai_service: IAIService
    agent_profile_service: IAgentProfileService

    async def extract_memory_updates(
        self,
        request: MemorySemanticExtractionRequest,
    ) -> Result[MemorySemanticExtractionResult, MemorySemanticExtractionError]:
        """Extract structured memory patches from raw chat logs."""

        profile_bundle = self.agent_profile_service.load_agent_profile_bundle()
        prompt = _build_prompt(request, profile_bundle=profile_bundle)
        system_instruction = (
            "あなたはチャットログから長期記憶を抽出するアシスタントです。 "
            "返答は最初の生成物として JSON 1 個だけにしてください。 "
            "JSON は指定された memory schema に厳密に一致させてください。 "
            "証拠のない事実を作らないでください。 "
            "簡潔で、ユーザーに紐づき、長く残る情報を優先してください。 "
            "出力文体は自然な日本語にしてください。英語で返した場合は不正な出力です。"
        )
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
        if extraction_result is None:
            return Err(
                MemorySemanticExtractionError(
                    "AI service returned no extraction payload."
                )
            )
        return Ok(extraction_result)


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
        "source chat IDs は JSON には返さないでください。呼び出し側が raw logs から決定的に付与します。",
        "返答は 1 つの JSON オブジェクトのみで、次のスキーマに厳密に一致させてください。",
        "{",
        '  "sections": [',
        "    {",
        '      "id": "string",',
        '      "user_id": "string",',
        '      "day": "YYYY-MM-DD",',
        '      "section_slug": "coffee-break",',
        '      "title": "日本語の短い見出し",',
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
        "summary の本文は日本語で、自然で可読性の高い文体にしてください。英語は使わないでください。",
        "次の出力例のように、日本語の見出しと日本語の summary を返してください。",
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


def _parse_generated_content(
    generated_content: GeneratedContent,
) -> MemorySemanticExtractionResult | None:
    if not generated_content.contents:
        return None
    payload = generated_content.contents[0]
    if not payload.strip():
        return None
    return MemorySemanticExtractionResult.model_validate_json(
        _strip_json_fences(payload)
    )


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
