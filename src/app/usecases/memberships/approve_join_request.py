"""Approve Join Request use case."""

import logging
from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.domain.aggregates.team_membership import TeamMembership
from app.domain.aggregates.team_membership_errors import (
    TeamMembershipTransitionErrorType,
)
from app.domain.value_objects import MembershipId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApproveJoinRequestResult:
    """Result of approving a join request."""

    id: str
    status: str


@dataclass(frozen=True)
class ApproveJoinRequestCommand(
    Request[Result[ApproveJoinRequestResult, UseCaseError]]
):
    """Command to approve a join request."""

    membership_id: str


class ApproveJoinRequestHandler(
    RequestHandler[
        ApproveJoinRequestCommand, Result[ApproveJoinRequestResult, UseCaseError]
    ]
):
    """Handler for ApproveJoinRequest command."""

    @inject
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def handle(
        self, request: ApproveJoinRequestCommand
    ) -> Result[ApproveJoinRequestResult, UseCaseError]:
        """Approve a join request."""
        membership_id_result = MembershipId.from_primitive(request.membership_id)

        if is_err(membership_id_result):
            return Err(
                UseCaseError(
                    type=ErrorType.VALIDATION_ERROR,
                    message="Invalid Membership ID format",
                )
            )

        membership_id = membership_id_result.unwrap()

        async with self._uow:
            membership_repo = self._uow.GetRepository(TeamMembership, MembershipId)

            membership_result = await membership_repo.get_by_id(membership_id)
            if is_err(membership_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.NOT_FOUND, message="Membership not found"
                    )
                )

            membership = membership_result.unwrap()

            activation_result = membership.activate()
            if is_err(activation_result):
                if (
                    activation_result.error.type
                    is TeamMembershipTransitionErrorType.INVALID_STATUS_TRANSITION
                ):
                    return Err(
                        UseCaseError(
                            type=ErrorType.VALIDATION_ERROR,
                            message=(
                                "Membership is not in PENDING status "
                                f"(current: {membership.status.value})"
                            ),
                        )
                    )
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=activation_result.error.message,
                    )
                )

            update_result = await membership_repo.update(membership)
            if is_err(update_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED, message=update_result.error.message
                    )
                )

            commit_result = await self._uow.commit()
            if is_err(commit_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED, message=commit_result.error.message
                    )
                )

            return Ok(
                ApproveJoinRequestResult(
                    id=membership.id.to_primitive(),
                    status=membership.status.value,
                )
            )
