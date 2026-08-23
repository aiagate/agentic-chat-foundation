"""Application boundaries for autonomous Discord discussions."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.contracts.messages.discussion import (
    AgentTurnDecision,
    AgentTurnDisposition,
    AgentTurnRecord,
    AutonomousTopicActivity,
    AutonomousTopicTurnRecord,
    DiscussionActivity,
    DiscussionHistoryItem,
    IncomingDiscussionMessage,
    ObservedDiscussionMessage,
    PrivateReflection,
    SentDiscussionMessage,
    TopicStimulus,
)


class IDiscussionRepository(Protocol):
    """Persist and query this bot's local view of a Discord discussion."""

    async def observe(
        self, message: IncomingDiscussionMessage
    ) -> ObservedDiscussionMessage: ...

    async def append_self_message(
        self,
        *,
        guild_id: str,
        channel_id: str,
        external_message_id: str,
        author_external_id: str,
        author_display_name: str,
        text: str,
        occurred_at: datetime,
    ) -> ObservedDiscussionMessage: ...

    async def recent_history(
        self,
        *,
        guild_id: str,
        channel_id: str,
        before_message_id: str,
        limit: int,
    ) -> list[DiscussionHistoryItem]: ...

    async def latest_history(
        self,
        *,
        guild_id: str,
        channel_id: str,
        limit: int,
    ) -> list[DiscussionHistoryItem]: ...

    async def messages_after(
        self,
        *,
        guild_id: str,
        channel_id: str,
        after_message_id: str,
        limit: int,
    ) -> list[ObservedDiscussionMessage]: ...

    async def recent_reflections(
        self,
        *,
        character_id: str,
        channel_id: str,
        limit: int,
    ) -> list[PrivateReflection]: ...

    async def activity(
        self,
        *,
        channel_id: str,
        character_id: str,
        window_started_at: datetime,
    ) -> DiscussionActivity: ...

    async def add_turn(
        self,
        *,
        trigger_message_id: str,
        channel_id: str,
        character_id: str,
        disposition: AgentTurnDisposition,
        decision: AgentTurnDecision | None,
        failure_reason: str | None = None,
    ) -> AgentTurnRecord: ...

    async def update_turn(
        self,
        *,
        turn_id: str,
        disposition: AgentTurnDisposition,
        published_external_message_ids: list[str] | None = None,
        failure_reason: str | None = None,
    ) -> None: ...


class IDiscussionMessageSender(Protocol):
    """Deliver selected public texts through this process's Discord account."""

    async def send(self, texts: list[str]) -> list[SentDiscussionMessage]: ...


class IAgentTurnEvaluator(Protocol):
    """Evaluate whether this process's single character should speak."""

    async def evaluate(
        self,
        *,
        message: ObservedDiscussionMessage,
        history: list[DiscussionHistoryItem],
        reflections: list[PrivateReflection],
    ) -> AgentTurnDecision: ...


class ILocalSpeechGuard(Protocol):
    """Apply local publication limits without coordinating with other bots."""

    def withholding_reason(
        self,
        *,
        message: ObservedDiscussionMessage,
        activity: DiscussionActivity,
        now: datetime,
    ) -> str | None: ...

    def window_started_at(self, now: datetime) -> datetime: ...


class IAutonomousTopicEvaluator(Protocol):
    """Decide whether the character should introduce a new topic."""

    async def evaluate(
        self,
        *,
        guild_id: str,
        channel_id: str,
        history: list[DiscussionHistoryItem],
        reflections: list[PrivateReflection],
        stimuli: list[TopicStimulus],
    ) -> AgentTurnDecision: ...


class IAutonomousTopicRepository(Protocol):
    """Persist local autonomous topic evaluations and activity."""

    async def topic_activity(
        self,
        *,
        guild_id: str,
        channel_id: str,
        character_id: str,
        window_started_at: datetime,
    ) -> AutonomousTopicActivity: ...

    async def add_topic_turn(
        self,
        *,
        guild_id: str,
        channel_id: str,
        character_id: str,
        baseline_message_id: str | None,
        disposition: AgentTurnDisposition,
        decision: AgentTurnDecision | None,
        failure_reason: str | None = None,
    ) -> AutonomousTopicTurnRecord: ...

    async def update_topic_turn(
        self,
        *,
        turn_id: str,
        disposition: AgentTurnDisposition,
        published_external_message_ids: list[str] | None = None,
        failure_reason: str | None = None,
    ) -> None: ...


class IAutonomousTopicGuard(Protocol):
    """Apply local idle, cadence, and publication limits."""

    def eligibility_reason(
        self,
        *,
        activity: AutonomousTopicActivity,
        now: datetime,
    ) -> str | None: ...

    def window_started_at(self, now: datetime) -> datetime: ...
