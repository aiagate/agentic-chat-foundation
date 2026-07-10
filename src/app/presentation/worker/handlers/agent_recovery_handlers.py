"""Scheduled recovery for durable workflow leases and retry timers."""

import logging

from flow_med import Mediator
from flow_res import is_err

from app.presentation.worker.registry import scheduled_task
from app.usecases.agent.recover_agent_runs import RecoverAgentRunsCommand

logger = logging.getLogger(__name__)


@scheduled_task(30)
async def recover_agent_runs_scheduled_task() -> None:
    """Make expired and due workflow work dispatchable again."""
    result = await Mediator.send_async(RecoverAgentRunsCommand())
    if is_err(result):
        logger.error("AgentRun recovery failed: %s", result.error.message)
    elif result.value:
        logger.info("Recovered %s durable agent work items", result.value)
