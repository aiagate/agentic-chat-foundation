"""Periodically consolidate conversation history into durable interpretations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.application.relationship import relationship_signal_id
from app.contracts.messages.relationship import (
    PersistedRelationshipSignal,
    RelationshipSignalKind,
    RelationshipSignalStatus,
)
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.unit_of_work import IUnitOfWorkFactory
from app.domain.aggregates.character_relationship import MIN_SIGNAL_CONFIDENCE
from app.domain.queries.long_term_memory_query import ILongTermMemoryQuery

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsolidateConversationHistoryResult:
    """Summary of one periodic conversation consolidation run."""

    target_count: int
    evaluated_chat_count: int
    deferred_chat_count: int
    profile_updated_count: int
    episode_upserted_count: int
    entity_upserted_count: int
    relationship_signal_count: int


@dataclass(frozen=True)
class ConsolidateConversationHistoryCommand(
    Request[Result[ConsolidateConversationHistoryResult, UseCaseError]]
):
    """Consolidate pending history for the active character."""

    reference_time: datetime | None = None


class ConsolidateConversationHistoryHandler(
    RequestHandler[
        ConsolidateConversationHistoryCommand,
        Result[ConsolidateConversationHistoryResult, UseCaseError],
    ]
):
    """Apply memory updates and confirmed relationship signals per batch."""

    @inject
    def __init__(
        self,
        uow_factory: IUnitOfWorkFactory,
        memory_consolidation_service: IMemoryConsolidationService,
        long_term_memory_query: ILongTermMemoryQuery,
        agent_profile_service: IAgentProfileService,
        character_id: str,
    ) -> None:
        self._uow_factory = uow_factory
        self._memory_consolidation_service = memory_consolidation_service
        self._long_term_memory_query = long_term_memory_query
        self._agent_profile_service = agent_profile_service
        self._character_id = character_id

    async def handle(
        self,
        request: ConsolidateConversationHistoryCommand,
    ) -> Result[ConsolidateConversationHistoryResult, UseCaseError]:
        try:
            reference_time = request.reference_time or datetime.now(UTC)
            if reference_time.tzinfo is None:
                reference_time = reference_time.replace(tzinfo=UTC)
            else:
                reference_time = reference_time.astimezone(UTC)
            read_uow = self._uow_factory.create()
            async with read_uow as active_read_uow:
                targets = await self._long_term_memory_query.list_pending_targets(
                    active_read_uow.GetRawChatLogQuery(),
                    character_id=self._character_id,
                    reference_time=reference_time,
                )
            profile = self._agent_profile_service.load_agent_profile_bundle()
            evaluated_chat_count = 0
            deferred_chat_count = 0
            profile_updated_count = 0
            episode_upserted_count = 0
            entity_upserted_count = 0
            relationship_signal_count = 0
            for target in targets:
                batch = await self._memory_consolidation_service.consolidate_chat_logs(
                    user_id=target.user_id,
                    day=target.day,
                    raw_logs=target.raw_logs,
                    reference_time=reference_time,
                )
                confirmed_signals: list[PersistedRelationshipSignal] = []
                for candidate in batch.relationship_signals:
                    if (
                        candidate.kind is RelationshipSignalKind.NEUTRAL
                        or candidate.confidence < MIN_SIGNAL_CONFIDENCE
                    ):
                        continue
                    observed_at = candidate.observed_at or reference_time
                    confirmed_signals.append(
                        PersistedRelationshipSignal(
                            id=relationship_signal_id(
                                character_id=target.character_id,
                                user_id=target.user_id,
                                kind=candidate.kind,
                                source_chat_ids=candidate.source_chat_ids,
                                status=RelationshipSignalStatus.CONFIRMED,
                            ),
                            character_id=target.character_id,
                            user_id=target.user_id,
                            kind=candidate.kind,
                            status=RelationshipSignalStatus.CONFIRMED,
                            confidence=candidate.confidence,
                            proposed_delta=profile.relationship.signal_deltas[
                                candidate.kind
                            ],
                            reason=candidate.reason,
                            source_chat_ids=candidate.source_chat_ids,
                            observed_at=observed_at,
                        )
                    )
                write_uow = self._uow_factory.create()
                async with write_uow as active_write_uow:
                    reconciled = await active_write_uow.GetCharacterRelationshipRepository().reconcile_confirmed(
                        character_id=target.character_id,
                        user_id=target.user_id,
                        evaluated_chat_ids=list(batch.evaluated_chat_ids),
                        signals=confirmed_signals,
                    )
                    if is_err(reconciled):
                        raise RuntimeError(reconciled.error.message)
                    marked = await active_write_uow.GetMemoryConsolidatedChatSourceRepository().mark_consolidated(
                        list(batch.evaluated_chat_ids),
                        consolidated_at=reference_time,
                    )
                    if is_err(marked):
                        raise RuntimeError(marked.error.message)
                    committed = await active_write_uow.commit()
                    if is_err(committed):
                        raise RuntimeError(committed.error.message)
                evaluated_chat_count += len(batch.evaluated_chat_ids)
                deferred_chat_count += len(batch.deferred_chat_ids)
                profile_updated_count += int(batch.profile_updated)
                episode_upserted_count += batch.episode_upserted_count
                entity_upserted_count += batch.entity_upserted_count
                relationship_signal_count += len(confirmed_signals)
            return Ok(
                ConsolidateConversationHistoryResult(
                    target_count=len(targets),
                    evaluated_chat_count=evaluated_chat_count,
                    deferred_chat_count=deferred_chat_count,
                    profile_updated_count=profile_updated_count,
                    episode_upserted_count=episode_upserted_count,
                    entity_upserted_count=entity_upserted_count,
                    relationship_signal_count=relationship_signal_count,
                )
            )
        except Exception as exc:
            logger.error(
                "Failed to consolidate conversation history: %s",
                exc,
                exc_info=True,
            )
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=f"Failed to consolidate conversation history: {exc}",
                )
            )
