"""Process one public Discord discussion message for the active character."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result

from app.contracts.messages.discussion import (
    AgentTurnDisposition,
    AgentTurnRecord,
    IncomingDiscussionMessage,
)
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.discussion import (
    IAgentTurnEvaluator,
    IDiscussionMessageSender,
    IDiscussionRepository,
    ILocalSpeechGuard,
)


@dataclass(frozen=True, slots=True)
class ProcessDiscussionMessageCommand(
    Request[Result[AgentTurnRecord | None, UseCaseError]]
):
    message: IncomingDiscussionMessage
    character_id: str
    self_external_id: str
    self_display_name: str
    sender: IDiscussionMessageSender
    publication_delay_seconds: float = 0.0


class ProcessDiscussionMessageHandler(
    RequestHandler[
        ProcessDiscussionMessageCommand,
        Result[AgentTurnRecord | None, UseCaseError],
    ]
):
    def __init__(
        self,
        repository: IDiscussionRepository,
        evaluator: IAgentTurnEvaluator,
        speech_guard: ILocalSpeechGuard,
    ) -> None:
        self._repository = repository
        self._evaluator = evaluator
        self._speech_guard = speech_guard

    async def handle(
        self, request: ProcessDiscussionMessageCommand
    ) -> Result[AgentTurnRecord | None, UseCaseError]:
        try:
            observed = await self._repository.observe(request.message)
            if not observed.is_new or observed.recovered:
                return Ok(None)

            history = await self._repository.recent_history(
                guild_id=observed.guild_id,
                channel_id=observed.channel_id,
                before_message_id=observed.message_id,
                limit=50,
            )
            reflections = await self._repository.recent_reflections(
                character_id=request.character_id,
                channel_id=observed.channel_id,
                limit=20,
            )
            try:
                decision = await self._evaluator.evaluate(
                    message=observed,
                    history=history,
                    reflections=reflections,
                )
            except Exception as exc:
                failed = await self._repository.add_turn(
                    trigger_message_id=observed.message_id,
                    channel_id=observed.channel_id,
                    character_id=request.character_id,
                    disposition=AgentTurnDisposition.FAILED,
                    decision=None,
                    failure_reason=str(exc),
                )
                return Ok(failed)

            if decision.speech_intent == "silent":
                silent = await self._repository.add_turn(
                    trigger_message_id=observed.message_id,
                    channel_id=observed.channel_id,
                    character_id=request.character_id,
                    disposition=AgentTurnDisposition.SILENT,
                    decision=decision,
                )
                return Ok(silent)

            proposed = await self._repository.add_turn(
                trigger_message_id=observed.message_id,
                channel_id=observed.channel_id,
                character_id=request.character_id,
                disposition=AgentTurnDisposition.PROPOSED,
                decision=decision,
            )
            if request.publication_delay_seconds > 0:
                await asyncio.sleep(request.publication_delay_seconds)

            newer_messages = await self._repository.messages_after(
                guild_id=observed.guild_id,
                channel_id=observed.channel_id,
                after_message_id=observed.message_id,
                limit=1,
            )
            if newer_messages:
                superseding_message = newer_messages[0]
                reason = (
                    "superseded_by_newer_message:"
                    f"{superseding_message.external_message_id}"
                )
                await self._repository.update_turn(
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

            now = datetime.now(UTC)
            activity = await self._repository.activity(
                channel_id=observed.channel_id,
                character_id=request.character_id,
                window_started_at=self._speech_guard.window_started_at(now),
            )
            withholding_reason = self._speech_guard.withholding_reason(
                message=observed,
                activity=activity,
                now=now,
            )
            if withholding_reason is not None:
                await self._repository.update_turn(
                    turn_id=proposed.turn_id,
                    disposition=AgentTurnDisposition.WITHHELD,
                    failure_reason=withholding_reason,
                )
                return Ok(
                    proposed.model_copy(
                        update={
                            "disposition": AgentTurnDisposition.WITHHELD,
                            "failure_reason": withholding_reason,
                        }
                    )
                )
            try:
                sent_messages = await request.sender.send(decision.texts)
                for sent in sent_messages:
                    await self._repository.append_self_message(
                        guild_id=observed.guild_id,
                        channel_id=observed.channel_id,
                        external_message_id=sent.external_message_id,
                        author_external_id=request.self_external_id,
                        author_display_name=request.self_display_name,
                        text=sent.text,
                        occurred_at=sent.occurred_at,
                    )
                await self._repository.update_turn(
                    turn_id=proposed.turn_id,
                    disposition=AgentTurnDisposition.PUBLISHED,
                    published_external_message_ids=[
                        item.external_message_id for item in sent_messages
                    ],
                )
                return Ok(
                    proposed.model_copy(
                        update={
                            "disposition": AgentTurnDisposition.PUBLISHED,
                            "published_external_message_ids": [
                                item.external_message_id for item in sent_messages
                            ],
                        }
                    )
                )
            except Exception as exc:
                await self._repository.update_turn(
                    turn_id=proposed.turn_id,
                    disposition=AgentTurnDisposition.FAILED,
                    failure_reason=str(exc),
                )
                return Err(
                    UseCaseError(
                        ErrorType.UNEXPECTED,
                        f"Discussion message delivery failed: {exc}",
                    )
                )
        except Exception as exc:
            return Err(UseCaseError(ErrorType.UNEXPECTED, str(exc)))
