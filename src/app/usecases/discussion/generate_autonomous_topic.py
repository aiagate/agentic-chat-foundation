"""Generate one internally initiated public Discord topic when locally eligible."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result

from app.contracts.messages.discussion import (
    AgentTurnDisposition,
    AutonomousTopicTurnRecord,
    TopicStimulus,
)
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.discussion import (
    IAutonomousTopicEvaluator,
    IAutonomousTopicGuard,
    IAutonomousTopicRepository,
    IDiscussionMessageSender,
    IDiscussionRepository,
)


@dataclass(frozen=True, slots=True)
class GenerateAutonomousTopicCommand(
    Request[Result[AutonomousTopicTurnRecord | None, UseCaseError]]
):
    guild_id: str
    channel_id: str
    character_id: str
    self_external_id: str
    self_display_name: str
    sender: IDiscussionMessageSender
    publication_delay_seconds: float = 0.0
    stimuli: list[TopicStimulus] = field(default_factory=list)


class GenerateAutonomousTopicHandler(
    RequestHandler[
        GenerateAutonomousTopicCommand,
        Result[AutonomousTopicTurnRecord | None, UseCaseError],
    ]
):
    """Own the complete boundary flow for one scheduled topic opportunity."""

    def __init__(
        self,
        discussion_repository: IDiscussionRepository,
        topic_repository: IAutonomousTopicRepository,
        evaluator: IAutonomousTopicEvaluator,
        guard: IAutonomousTopicGuard,
    ) -> None:
        self._discussion_repository = discussion_repository
        self._topic_repository = topic_repository
        self._evaluator = evaluator
        self._guard = guard

    async def handle(
        self, request: GenerateAutonomousTopicCommand
    ) -> Result[AutonomousTopicTurnRecord | None, UseCaseError]:
        try:
            now = datetime.now(UTC)
            activity = await self._topic_repository.topic_activity(
                guild_id=request.guild_id,
                channel_id=request.channel_id,
                character_id=request.character_id,
                window_started_at=self._guard.window_started_at(now),
            )
            if self._guard.eligibility_reason(activity=activity, now=now) is not None:
                return Ok(None)

            history = await self._discussion_repository.latest_history(
                guild_id=request.guild_id,
                channel_id=request.channel_id,
                limit=50,
            )
            reflections = await self._discussion_repository.recent_reflections(
                character_id=request.character_id,
                channel_id=request.channel_id,
                limit=20,
            )
            try:
                decision = await self._evaluator.evaluate(
                    guild_id=request.guild_id,
                    channel_id=request.channel_id,
                    history=history,
                    reflections=reflections,
                    stimuli=request.stimuli,
                )
            except Exception as exc:
                failed = await self._topic_repository.add_topic_turn(
                    guild_id=request.guild_id,
                    channel_id=request.channel_id,
                    character_id=request.character_id,
                    baseline_message_id=activity.latest_message_id,
                    disposition=AgentTurnDisposition.FAILED,
                    decision=None,
                    failure_reason=str(exc),
                )
                return Ok(failed)

            if decision.speech_intent == "silent":
                silent = await self._topic_repository.add_topic_turn(
                    guild_id=request.guild_id,
                    channel_id=request.channel_id,
                    character_id=request.character_id,
                    baseline_message_id=activity.latest_message_id,
                    disposition=AgentTurnDisposition.SILENT,
                    decision=decision,
                )
                return Ok(silent)

            proposed = await self._topic_repository.add_topic_turn(
                guild_id=request.guild_id,
                channel_id=request.channel_id,
                character_id=request.character_id,
                baseline_message_id=activity.latest_message_id,
                disposition=AgentTurnDisposition.PROPOSED,
                decision=decision,
            )
            if request.publication_delay_seconds > 0:
                await asyncio.sleep(request.publication_delay_seconds)

            current = await self._topic_repository.topic_activity(
                guild_id=request.guild_id,
                channel_id=request.channel_id,
                character_id=request.character_id,
                window_started_at=self._guard.window_started_at(datetime.now(UTC)),
            )
            if current.latest_message_id != activity.latest_message_id:
                reason = f"superseded_by_newer_message:{current.latest_message_id}"
                await self._topic_repository.update_topic_turn(
                    turn_id=proposed.turn_id,
                    disposition=AgentTurnDisposition.SUPERSEDED,
                    failure_reason=reason,
                )
                return Ok(
                    proposed.model_copy(
                        update={
                            "disposition": AgentTurnDisposition.SUPERSEDED,
                            "failure_reason": reason,
                        }
                    )
                )

            try:
                sent_messages = await request.sender.send(decision.texts)
                for sent in sent_messages:
                    await self._discussion_repository.append_self_message(
                        guild_id=request.guild_id,
                        channel_id=request.channel_id,
                        external_message_id=sent.external_message_id,
                        author_external_id=request.self_external_id,
                        author_display_name=request.self_display_name,
                        text=sent.text,
                        occurred_at=sent.occurred_at,
                    )
                published_ids = [item.external_message_id for item in sent_messages]
                await self._topic_repository.update_topic_turn(
                    turn_id=proposed.turn_id,
                    disposition=AgentTurnDisposition.PUBLISHED,
                    published_external_message_ids=published_ids,
                )
                return Ok(
                    proposed.model_copy(
                        update={
                            "disposition": AgentTurnDisposition.PUBLISHED,
                            "published_external_message_ids": published_ids,
                        }
                    )
                )
            except Exception as exc:
                await self._topic_repository.update_topic_turn(
                    turn_id=proposed.turn_id,
                    disposition=AgentTurnDisposition.FAILED,
                    failure_reason=str(exc),
                )
                return Err(
                    UseCaseError(
                        ErrorType.UNEXPECTED,
                        f"Autonomous topic delivery failed: {exc}",
                    )
                )
        except Exception as exc:
            return Err(UseCaseError(ErrorType.UNEXPECTED, str(exc)))
