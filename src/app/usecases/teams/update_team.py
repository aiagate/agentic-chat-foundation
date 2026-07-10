"""Update Team use case."""

import logging
from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, combine_all, is_err
from injector import inject

from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.domain.aggregates.team import Team
from app.domain.repositories import RepositoryErrorType
from app.domain.value_objects import TeamId, TeamName

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpdateTeamResult:
    id: str


@dataclass(frozen=True)
class UpdateTeamCommand(Request[Result[UpdateTeamResult, UseCaseError]]):
    """Command to update team name."""

    team_id: str
    new_name: str


class UpdateTeamHandler(
    RequestHandler[UpdateTeamCommand, Result[UpdateTeamResult, UseCaseError]]
):
    """Handler for UpdateTeam command."""

    @inject
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def handle(
        self, request: UpdateTeamCommand
    ) -> Result[UpdateTeamResult, UseCaseError]:
        """Update team name and return updated team info within a Result."""
        # Validate inputs
        team_id_result = TeamId.from_primitive(request.team_id)
        team_name_result = TeamName.from_primitive(request.new_name)

        combined_result = combine_all((team_id_result, team_name_result)).map_err(
            lambda e: UseCaseError(
                type=ErrorType.VALIDATION_ERROR,
                message=", ".join(str(exc) for exc in e.exceptions),
            )
        )
        if is_err(combined_result):
            return combined_result

        team_id, new_team_name = combined_result.unwrap()

        async with self._uow:
            team_repo = self._uow.GetRepository(Team, TeamId)

            # Get existing team
            get_result = await team_repo.get_by_id(team_id)
            if is_err(get_result):
                if get_result.error.type == RepositoryErrorType.NOT_FOUND:
                    return Err(
                        UseCaseError(
                            type=ErrorType.NOT_FOUND,
                            message=f"Team with id {request.team_id} not found",
                        )
                    )
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=get_result.error.message,
                    )
                )

            team = get_result.unwrap()

            # Update team name
            team.change_name(new_team_name)

            # Save updated team (optimistic locking happens here)
            update_result = await team_repo.update(team)
            if is_err(update_result):
                if update_result.error.type == RepositoryErrorType.VERSION_CONFLICT:
                    return Err(
                        UseCaseError(
                            type=ErrorType.CONCURRENCY_CONFLICT,
                            message=(
                                f"Team with id {request.team_id} was modified by "
                                "another user. Please reload and try again."
                            ),
                        )
                    )
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=update_result.error.message,
                    )
                )

            # Commit transaction
            commit_result = (await self._uow.commit()).map_err(
                lambda e: UseCaseError(type=ErrorType.UNEXPECTED, message=e.message)
            )

            if is_err(commit_result):
                return commit_result

            updated_team = update_result.unwrap()

            return Ok(UpdateTeamResult(id=updated_team.id.to_primitive()))
