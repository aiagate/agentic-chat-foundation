import asyncio
import logging
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flow_med import Mediator
from injector import Injector

from app import container
from app.infrastructure.database import init_db
from app.presentation.worker.registry import EventRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def load_environment() -> None:
    """Load environment variables from .env files."""
    root_dir = Path(__file__).parent.parent.parent.parent.parent
    env_local = root_dir / ".env.local"
    if env_local.exists():
        load_dotenv(env_local, override=True)
        return
    env_file = root_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)


async def _run_periodic_task(
    interval: int,
    func: Callable[[], Awaitable[None]],
    *,
    initial_delay_seconds: float = 0.0,
) -> None:
    """Run a function periodically with the given interval."""
    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)
    while True:
        try:
            await func()
        except Exception as e:
            logger.error(
                "Error in scheduled task %s: %s",
                func.__name__,
                e,
                exc_info=True,
            )
        await asyncio.sleep(interval)


def _initial_delay_until_run(
    now: datetime,
    run_time: time | None,
) -> float:
    """Return the delay until the next aligned run."""

    if run_time is None:
        return 0.0

    scheduled_today = datetime.combine(now.date(), run_time, tzinfo=now.tzinfo)
    if now <= scheduled_today:
        return (scheduled_today - now).total_seconds()

    scheduled_tomorrow = datetime.combine(
        now.date() + timedelta(days=1),
        run_time,
        tzinfo=now.tzinfo,
    )
    return (scheduled_tomorrow - now).total_seconds()


def _start_scheduled_tasks(
    registry: EventRegistry,
    *,
    now: datetime | None = None,
) -> list[asyncio.Task[None]]:
    """Start all scheduled worker tasks registered by decorators."""

    tasks: list[asyncio.Task[None]] = []
    for interval, task_func in registry.scheduled_tasks:
        schedule_timezone = getattr(task_func, "schedule_timezone", None)
        if not isinstance(schedule_timezone, ZoneInfo):
            schedule_timezone = datetime.now().astimezone().tzinfo
        current_time = now or datetime.now(schedule_timezone)
        if now is not None and schedule_timezone is not None:
            current_time = now.astimezone(schedule_timezone)
        schedule_run_time = getattr(task_func, "schedule_run_time", None)
        if not isinstance(schedule_run_time, time):
            schedule_run_time = None
        # `current_time` is aligned to the host's local timezone here.
        initial_delay_seconds = _initial_delay_until_run(
            current_time,
            schedule_run_time,
        )
        task = asyncio.create_task(
            _run_periodic_task(
                interval,
                task_func,
                initial_delay_seconds=initial_delay_seconds,
            )
        )
        tasks.append(task)
        logger.info(
            "Started scheduled task: %s (interval: %ss, initial_delay: %ss)",
            task_func.__name__,
            interval,
            initial_delay_seconds,
        )
    return tasks


async def main() -> None:
    """Worker entry point."""
    logger.info("Starting Worker process...")

    # 0. 環境変数の読み込み
    load_environment()

    # 1. データベースとDIコンテナの初期化
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
    init_db(db_url, echo=False)

    injector = Injector([container.configure])

    # Mediatorの初期化
    Mediator.initialize(injector)

    # 2. 定期タスクの登録
    import app.presentation.worker.handlers as _  # type: ignore[reportUnusedImport] # noqa: F401
    from app.presentation.worker.registry import registry

    if os.getenv("WORKER_RUN_ONCE") == "1":
        for _, task_func in registry.scheduled_tasks:
            await task_func()
        logger.info("Worker run-once completed.")
        return

    _start_scheduled_tasks(registry)

    logger.info("Worker process initialized for periodic memory organization.")

    # 4. 停止信号の処理

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_stop_signal() -> None:
        logger.info("Stop signal received.")
        stop_event.set()

    # Windows環境等での互換性を考慮したシグナルハンドリング
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_stop_signal)
        except NotImplementedError:
            # add_signal_handler がサポートされていない環境（Windows等）
            pass

    try:
        # 停止信号を待機
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Shutting down Worker process...")


def start() -> None:
    """Synchronous entry point for console scripts and Docker."""

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    start()
