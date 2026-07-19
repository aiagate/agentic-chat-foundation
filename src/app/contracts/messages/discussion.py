"""Messages exchanged by the autonomous Discord discussion flow."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DiscussionAuthorKind(StrEnum):
    """Public actor types observable through Discord."""

    HUMAN = "human"
    BOT = "bot"
    SELF = "self"


class AgentTurnDisposition(StrEnum):
    """Durable outcome of one local agent evaluation."""

    SILENT = "silent"
    PROPOSED = "proposed"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    WITHHELD = "withheld"
    FAILED = "failed"


class IncomingDiscussionMessage(BaseModel):
    """One public Discord message observed by this bot process."""

    model_config = ConfigDict(extra="forbid")

    external_message_id: str = Field(min_length=1)
    guild_id: str = Field(min_length=1)
    channel_id: str = Field(min_length=1)
    author_external_id: str = Field(min_length=1)
    author_display_name: str = Field(min_length=1)
    author_kind: DiscussionAuthorKind
    text: str = Field(min_length=1)
    mentioned_self: bool = False
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    recovered: bool = False


class ObservedDiscussionMessage(IncomingDiscussionMessage):
    """Canonical local identity assigned to an observed Discord message."""

    message_id: str = Field(min_length=1)
    is_new: bool = True


class DiscussionHistoryItem(BaseModel):
    """Prompt-ready public discussion history item."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    external_message_id: str
    author_external_id: str
    author_display_name: str
    author_kind: DiscussionAuthorKind
    text: str
    occurred_at: datetime


class DiscussionParticipantContext(BaseModel):
    """Structured identity of one participant in an LLM discussion context."""

    model_config = ConfigDict(extra="forbid")

    external_id: str
    display_name: str
    kind: DiscussionAuthorKind


class DiscussionContextMessage(BaseModel):
    """One public Discord event represented without mixing metadata into text."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    external_message_id: str
    author: DiscussionParticipantContext
    text: str
    occurred_at: datetime


class DiscussionTurnContext(BaseModel):
    """Structured public event sequence supplied for one agent decision."""

    model_config = ConfigDict(extra="forbid")

    context_type: Literal["discord_discussion_turn"] = "discord_discussion_turn"
    guild_id: str
    channel_id: str
    latest_message_id: str
    messages: list[DiscussionContextMessage]


class PrivateReflection(BaseModel):
    """Short private state explicitly produced by the character."""

    model_config = ConfigDict(extra="forbid")

    observation: str = Field(default="", max_length=500)
    stance: str = Field(default="", max_length=500)
    emotion: str = Field(default="", max_length=200)
    next_intent: str = Field(default="", max_length=500)
    open_question: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_meaningful_private_state(self) -> PrivateReflection:
        values = (
            self.observation,
            self.stance,
            self.emotion,
            self.next_intent,
            self.open_question or "",
        )
        if not any(value.strip() for value in values):
            raise ValueError("private reflection must contain meaningful state")
        return self


class AgentTurnDecision(BaseModel):
    """Validated public/silent decision returned by one character."""

    model_config = ConfigDict(extra="forbid")

    speech_intent: Literal["speak", "silent"]
    texts: list[str] = Field(default_factory=list)
    private_reflection: PrivateReflection

    @model_validator(mode="after")
    def validate_intent_and_texts(self) -> AgentTurnDecision:
        normalized = [text.strip() for text in self.texts if text.strip()]
        self.texts = normalized
        if self.speech_intent == "speak" and not normalized:
            raise ValueError("speak decisions require at least one text")
        if self.speech_intent == "silent" and normalized:
            raise ValueError("silent decisions cannot contain public texts")
        return self


class AgentTurnRecord(BaseModel):
    """Persisted local evaluation state."""

    model_config = ConfigDict(extra="forbid")

    turn_id: str
    trigger_message_id: str
    character_id: str
    disposition: AgentTurnDisposition
    private_reflection: PrivateReflection | None = None
    proposed_texts: list[str] = Field(default_factory=list)
    published_external_message_ids: list[str] = Field(default_factory=list)
    failure_reason: str | None = None
    created_at: datetime


class DiscussionActivity(BaseModel):
    """Local public-activity counters used by the speech guard."""

    model_config = ConfigDict(extra="forbid")

    consecutive_bot_messages: int = Field(ge=0)
    last_published_at: datetime | None = None
    published_turns_in_window: int = Field(ge=0)


class SentDiscussionMessage(BaseModel):
    """One concrete Discord message created by the local bot account."""

    model_config = ConfigDict(extra="forbid")

    external_message_id: str
    text: str
    occurred_at: datetime


class TopicStimulus(BaseModel):
    """Optional external inspiration for a future autonomous topic decision."""

    model_config = ConfigDict(extra="forbid")

    source_kind: str = Field(min_length=1, max_length=50)
    source_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=2000)
    url: str | None = Field(default=None, max_length=2000)
    occurred_at: datetime | None = None


class AutonomousTopicContext(BaseModel):
    """Structured context for an internally initiated discussion topic."""

    model_config = ConfigDict(extra="forbid")

    context_type: Literal["autonomous_topic_generation"] = "autonomous_topic_generation"
    guild_id: str
    channel_id: str
    generated_at: datetime
    messages: list[DiscussionContextMessage]
    stimuli: list[TopicStimulus] = Field(default_factory=list)


class AutonomousTopicActivity(BaseModel):
    """Local activity used to decide whether topic generation may run."""

    model_config = ConfigDict(extra="forbid")

    latest_message_id: str | None = None
    latest_message_at: datetime | None = None
    last_evaluated_at: datetime | None = None
    published_topics_in_window: int = Field(ge=0)


class AutonomousTopicTurnRecord(BaseModel):
    """Durable outcome of one internally initiated topic evaluation."""

    model_config = ConfigDict(extra="forbid")

    turn_id: str
    guild_id: str
    channel_id: str
    character_id: str
    baseline_message_id: str | None = None
    disposition: AgentTurnDisposition
    private_reflection: PrivateReflection | None = None
    proposed_texts: list[str] = Field(default_factory=list)
    published_external_message_ids: list[str] = Field(default_factory=list)
    failure_reason: str | None = None
    created_at: datetime
