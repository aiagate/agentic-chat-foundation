"""Application behavior supporting one autonomous Discord discussion bot."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flow_res import is_err

from app.contracts.messages.discussion import (
    AgentTurnDecision,
    AutonomousTopicActivity,
    AutonomousTopicContext,
    DiscussionActivity,
    DiscussionContextMessage,
    DiscussionHistoryItem,
    DiscussionParticipantContext,
    DiscussionTurnContext,
    ObservedDiscussionMessage,
    PrivateReflection,
    TopicStimulus,
)
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.discussion import (
    IAgentTurnEvaluator,
    IAutonomousTopicEvaluator,
    IAutonomousTopicGuard,
    ILocalSpeechGuard,
)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class StructuredAgentTurnEvaluator(IAgentTurnEvaluator):
    """Ask the active character for a validated public/silent decision."""

    def __init__(
        self,
        ai_service: IAIService,
        agent_profile_service: IAgentProfileService,
    ) -> None:
        self._ai_service = ai_service
        self._agent_profile_service = agent_profile_service

    async def evaluate(
        self,
        *,
        message: ObservedDiscussionMessage,
        history: list[DiscussionHistoryItem],
        reflections: list[PrivateReflection],
    ) -> AgentTurnDecision:
        profile = self._agent_profile_service.load_agent_profile_bundle()
        generated = await self._ai_service.generate_content(
            _discussion_context(message, history).model_dump_json(indent=2),
            [],
            system_instruction=_system_instruction(
                profile.persona_context,
                reflections,
            ),
            tool_definitions=[],
            tool_results=[],
        )
        if is_err(generated):
            raise RuntimeError(generated.error.message)
        if generated.value.tool_calls:
            raise ValueError("Discussion decisions cannot contain tool calls")
        if len(generated.value.contents) != 1:
            raise ValueError("Discussion decision must contain exactly one JSON value")
        return _decode_decision(generated.value.contents[0])


class StructuredAutonomousTopicEvaluator(IAutonomousTopicEvaluator):
    """Ask the active character whether to introduce an original topic."""

    def __init__(
        self,
        ai_service: IAIService,
        agent_profile_service: IAgentProfileService,
    ) -> None:
        self._ai_service = ai_service
        self._agent_profile_service = agent_profile_service

    async def evaluate(
        self,
        *,
        guild_id: str,
        channel_id: str,
        history: list[DiscussionHistoryItem],
        reflections: list[PrivateReflection],
        stimuli: list[TopicStimulus],
    ) -> AgentTurnDecision:
        profile = self._agent_profile_service.load_agent_profile_bundle()
        context = AutonomousTopicContext(
            guild_id=guild_id,
            channel_id=channel_id,
            generated_at=datetime.now(UTC),
            messages=[_context_message(item) for item in history],
            stimuli=stimuli,
        )
        generated = await self._ai_service.generate_content(
            context.model_dump_json(indent=2),
            [],
            system_instruction=_autonomous_topic_system_instruction(
                profile.persona_context,
                reflections,
            ),
            tool_definitions=[],
            tool_results=[],
        )
        if is_err(generated):
            raise RuntimeError(generated.error.message)
        if generated.value.tool_calls:
            raise ValueError("Autonomous topic decisions cannot contain tool calls")
        if len(generated.value.contents) != 1:
            raise ValueError(
                "Autonomous topic decision must contain exactly one JSON value"
            )
        return _decode_decision(generated.value.contents[0])


@dataclass(frozen=True, slots=True)
class LocalSpeechGuardSettings:
    """Configurable local limits; no value requires another bot's state."""

    max_consecutive_bot_messages: int = 8
    cooldown_seconds: int = 20
    rate_window_seconds: int = 300
    max_published_turns_per_window: int = 5


class LocalSpeechGuard(ILocalSpeechGuard):
    """Prevent unbounded local publication while still evaluating every event."""

    def __init__(self, settings: LocalSpeechGuardSettings) -> None:
        self._settings = settings

    @property
    def rate_window(self) -> timedelta:
        return timedelta(seconds=self._settings.rate_window_seconds)

    def withholding_reason(
        self,
        *,
        message: ObservedDiscussionMessage,
        activity: DiscussionActivity,
        now: datetime,
    ) -> str | None:
        if (
            activity.consecutive_bot_messages
            >= self._settings.max_consecutive_bot_messages
        ):
            return "consecutive_bot_message_limit"
        if (
            activity.published_turns_in_window
            >= self._settings.max_published_turns_per_window
        ):
            return "local_publication_rate_limit"
        if activity.last_published_at is None or message.mentioned_self:
            return None
        elapsed = _as_utc(now) - _as_utc(activity.last_published_at)
        if elapsed < timedelta(seconds=self._settings.cooldown_seconds):
            return "local_publication_cooldown"
        return None

    def window_started_at(self, now: datetime) -> datetime:
        return _as_utc(now) - self.rate_window


@dataclass(frozen=True, slots=True)
class LocalAutonomousTopicGuardSettings:
    """Independent limits for internally initiated topic generation."""

    idle_seconds: int = 1800
    minimum_evaluation_interval_seconds: int = 900
    rate_window_seconds: int = 86400
    max_published_topics_per_window: int = 3


class LocalAutonomousTopicGuard(IAutonomousTopicGuard):
    """Avoid interrupting active conversations or flooding a channel."""

    def __init__(self, settings: LocalAutonomousTopicGuardSettings) -> None:
        self._settings = settings

    def eligibility_reason(
        self,
        *,
        activity: AutonomousTopicActivity,
        now: datetime,
    ) -> str | None:
        current = _as_utc(now)
        if activity.latest_message_at is not None:
            idle_for = current - _as_utc(activity.latest_message_at)
            if idle_for < timedelta(seconds=self._settings.idle_seconds):
                return "channel_not_idle"
        if activity.last_evaluated_at is not None:
            since_evaluation = current - _as_utc(activity.last_evaluated_at)
            if since_evaluation < timedelta(
                seconds=self._settings.minimum_evaluation_interval_seconds
            ):
                return "topic_evaluation_cooldown"
        if (
            activity.published_topics_in_window
            >= self._settings.max_published_topics_per_window
        ):
            return "topic_publication_rate_limit"
        return None

    def window_started_at(self, now: datetime) -> datetime:
        return _as_utc(now) - timedelta(seconds=self._settings.rate_window_seconds)


def _discussion_context(
    message: ObservedDiscussionMessage,
    history: list[DiscussionHistoryItem],
) -> DiscussionTurnContext:
    messages = [_context_message(item) for item in history]
    messages.append(
        DiscussionContextMessage(
            message_id=message.message_id,
            external_message_id=message.external_message_id,
            author=DiscussionParticipantContext(
                external_id=message.author_external_id,
                display_name=message.author_display_name,
                kind=message.author_kind,
            ),
            text=message.text,
            occurred_at=message.occurred_at,
        )
    )
    return DiscussionTurnContext(
        guild_id=message.guild_id,
        channel_id=message.channel_id,
        latest_message_id=message.message_id,
        messages=messages,
    )


def _context_message(item: DiscussionHistoryItem) -> DiscussionContextMessage:
    return DiscussionContextMessage(
        message_id=item.message_id,
        external_message_id=item.external_message_id,
        author=DiscussionParticipantContext(
            external_id=item.author_external_id,
            display_name=item.author_display_name,
            kind=item.author_kind,
        ),
        text=item.text,
        occurred_at=item.occurred_at,
    )


def _system_instruction(
    persona_context: str,
    reflections: list[PrivateReflection],
) -> str:
    reflection_payload = [item.model_dump(mode="json") for item in reflections]
    return f"""{persona_context}

You are independently participating in a public Discord discussion. Other bots
are external participants. Decide whether you genuinely have something useful
to say. Silence is normal and preferable to repetition. Your private state is
never visible to other participants.

The user input is one JSON object containing an ordered public Discord event
sequence. Participant identity and message text are separate data fields.
latest_message_id identifies the event that triggered this decision.

Recent private reflections (private and possibly uncertain):
{json.dumps(reflection_payload, ensure_ascii=False)}

Return exactly one JSON object and no Markdown. The schema is:
{{
  "speech_intent": "speak" | "silent",
  "texts": ["public Discord text"],
  "private_reflection": {{
    "observation": "short observation",
    "stance": "short current stance",
    "emotion": "short emotional state",
    "next_intent": "what you may do next",
    "open_question": "unresolved question or null"
  }}
}}

When speech_intent is silent, texts must be empty. When it is speak, texts must
contain every public message you intend to send. Do not expose private_reflection
inside texts. Each text should be at most 2000 characters.
"""


def _autonomous_topic_system_instruction(
    persona_context: str,
    reflections: list[PrivateReflection],
) -> str:
    reflection_payload = [item.model_dump(mode="json") for item in reflections]
    return f"""{persona_context}

You may independently introduce one new topic into a public Discord discussion.
Decide whether you genuinely have something worth bringing up now. Silence is
normal. Prefer a specific observation, question, or unresolved thought that fits
your character over generic conversation starters.

The user input is JSON containing recent public messages and an optional stimuli
array. In the current implementation stimuli is empty. Future implementations may
add attributed internet information there. Never invent current news, sources,
URLs, quotations, or claims of having browsed the internet. Without stimuli, use
only your stable interests, lived persona, and the supplied public history.

Do not repeat a recent topic. Do not pretend another participant asked you a
question. A public topic should be understandable on its own and invite discussion
without demanding a reply. Your private state is never visible to participants.

Recent private reflections (private and possibly uncertain):
{json.dumps(reflection_payload, ensure_ascii=False)}

Return exactly one JSON object and no Markdown. The schema is:
{{
  "speech_intent": "speak" | "silent",
  "texts": ["public Discord text"],
  "private_reflection": {{
    "observation": "short observation",
    "stance": "short current stance",
    "emotion": "short emotional state",
    "next_intent": "what you may do next",
    "open_question": "unresolved question or null"
  }}
}}

When speech_intent is silent, texts must be empty. When it is speak, texts must
contain every public message you intend to send. Do not expose private_reflection
inside texts. Each text should be at most 2000 characters.
"""


def _decode_decision(value: str) -> AgentTurnDecision:
    payload = _JSON_FENCE.sub("", value.strip())
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Discussion decision is not valid JSON") from exc
    return AgentTurnDecision.model_validate(decoded)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
