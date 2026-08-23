"""Registry for event handlers to allow decorator-based registration."""

from collections.abc import Awaitable, Callable

ScheduledTask = Callable[[], Awaitable[None]]


class EventRegistry:
    """Registry for periodic worker tasks."""

    def __init__(self) -> None:
        self._scheduled_tasks: list[tuple[int, ScheduledTask]] = []

    def scheduled(self, interval_seconds: int):
        """Decorator to register a function as a periodic scheduled task."""

        def decorator(func: ScheduledTask) -> ScheduledTask:
            self._scheduled_tasks.append((interval_seconds, func))
            return func

        return decorator

    @property
    def scheduled_tasks(self) -> list[tuple[int, ScheduledTask]]:
        """Return all collected scheduled tasks with their intervals."""
        return self._scheduled_tasks


# グローバルなレジストリインスタンス
registry = EventRegistry()
scheduled_task = registry.scheduled
