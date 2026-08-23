"""Pure application policies for relationship-aware responses."""

from __future__ import annotations

import hashlib
import logging

from flow_res import is_err

from app.contracts.messages.conversation import AcceptedMessage
from app.contracts.messages.relationship import (
    CharacterRelationshipDefinition,
    PersistedRelationshipSignal,
    RelationshipBehaviorDirective,
    RelationshipSignalEvaluationRequest,
    RelationshipSignalKind,
    RelationshipSignalStatus,
    RelationshipStateView,
)
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.relationship import (
    IRelationshipInteractionProcessor,
    IRelationshipSignalEvaluator,
)
from app.contracts.ports.unit_of_work import IUnitOfWorkFactory
from app.domain.aggregates.character_relationship import MIN_SIGNAL_CONFIDENCE

logger = logging.getLogger(__name__)


class RelationshipInteractionProcessor(IRelationshipInteractionProcessor):
    """Classify and record the current user message as provisional evidence."""

    def __init__(
        self,
        evaluator: IRelationshipSignalEvaluator,
        profile_service: IAgentProfileService,
        uow_factory: IUnitOfWorkFactory,
    ) -> None:
        self._evaluator = evaluator
        self._profile_service = profile_service
        self._uow_factory = uow_factory

    async def process(self, message: AcceptedMessage) -> None:
        evaluation = await self._evaluator.evaluate(
            RelationshipSignalEvaluationRequest(
                mode="immediate",
                character_id=message.character_id,
                user_id=message.user_id,
                source_chat_ids=[message.message_id],
                conversation_text=message.text,
                observed_at=message.occurred_at,
            )
        )
        if is_err(evaluation):
            logger.warning(
                "Immediate relationship signal evaluation failed: character_id=%s user_id=%s message_id=%s error=%s",
                message.character_id,
                message.user_id,
                message.message_id,
                evaluation.error.message,
            )
            return
        candidate = evaluation.value
        if (
            candidate.kind is RelationshipSignalKind.NEUTRAL
            or candidate.confidence < MIN_SIGNAL_CONFIDENCE
        ):
            return
        definition = self._profile_service.load_agent_profile_bundle().relationship
        event_id = relationship_signal_id(
            character_id=message.character_id,
            user_id=message.user_id,
            kind=candidate.kind,
            source_chat_ids=[message.message_id],
            status=RelationshipSignalStatus.PROVISIONAL,
        )
        signal = PersistedRelationshipSignal(
            id=event_id,
            character_id=message.character_id,
            user_id=message.user_id,
            kind=candidate.kind,
            status=RelationshipSignalStatus.PROVISIONAL,
            confidence=candidate.confidence,
            proposed_delta=definition.signal_deltas[candidate.kind],
            reason=candidate.reason,
            source_chat_ids=[message.message_id],
            observed_at=message.occurred_at,
        )
        async with self._uow_factory.create() as uow:
            recorded = (
                await uow.GetCharacterRelationshipRepository().record_provisional(
                    signal
                )
            )
            if is_err(recorded):
                logger.warning(
                    "Immediate relationship signal persistence failed: event_id=%s error=%s",
                    event_id,
                    recorded.error.message,
                )
                return
            committed = await uow.commit()
            if is_err(committed):
                logger.warning(
                    "Immediate relationship signal commit failed: event_id=%s error=%s",
                    event_id,
                    committed.error.message,
                )


def relationship_signal_id(
    *,
    character_id: str,
    user_id: str,
    kind: RelationshipSignalKind,
    source_chat_ids: list[str],
    status: RelationshipSignalStatus,
) -> str:
    """Return a stable idempotency key for one semantic signal."""

    payload = "\x1f".join(
        (
            character_id,
            user_id,
            kind.value,
            status.value,
            *sorted(set(source_chat_ids)),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_relationship_behavior(
    *,
    definition: CharacterRelationshipDefinition,
    state: RelationshipStateView,
    message_id: str,
) -> RelationshipBehaviorDirective:
    """Select one weighted behavior deterministically for an agent turn."""

    stage = definition.stage(state.stage_id)
    seed = "\x1f".join(
        (
            state.character_id,
            state.user_id,
            message_id,
            str(definition.schema_version),
        )
    ).encode("utf-8")
    bucket = int.from_bytes(hashlib.sha256(seed).digest(), "big") % sum(
        behavior.weight for behavior in stage.behaviors
    )
    cumulative = 0
    selected = stage.behaviors[-1]
    for behavior in stage.behaviors:
        cumulative += behavior.weight
        if bucket < cumulative:
            selected = behavior
            break
    return RelationshipBehaviorDirective(
        stage_id=state.stage_id,
        behavior_id=selected.id,
        instruction=selected.instruction,
    )


def render_relationship_behavior(directive: RelationshipBehaviorDirective) -> str:
    """Render a low-priority runtime behavior instruction."""

    return "\n".join(
        (
            "Relationship behavior for this turn:",
            f"- {directive.instruction}",
            "- Treat this as a subtle style cue below the persona and safety rules.",
            "- Never reveal a numeric affection value or relationship stage.",
        )
    )
