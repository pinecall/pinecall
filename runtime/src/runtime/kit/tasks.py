"""Work started and not awaited: held so it is not lost, said when it breaks, cancelled together."""

import asyncio
import logging
from collections.abc import Coroutine

from runtime.kit.loops import is_cancellation

logger = logging.getLogger(__name__)


class Tasks:
    """The tasks one owner started: each kept until it ends, its failure logged, all stopped at once."""

    def __init__(self, what: str) -> None:
        self.what = what
        self._running: set[asyncio.Task[object]] = set()

    def __len__(self) -> int:
        return len(self._running)

    def spawn(self, work: Coroutine[object, object, object], *, name: str | None = None) -> asyncio.Task[object]:
        """Start the work; the event loop keeps only a weak reference, so it is held here until it ends."""
        task = asyncio.create_task(work, name=name)
        self._running.add(task)
        task.add_done_callback(self._discard)
        return task

    async def cancel(self) -> None:
        """Cancel what still runs and wait for each to end."""
        running = list(self._running)
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)

    def _discard(self, task: asyncio.Task[object]) -> None:
        self._running.discard(task)
        if task.cancelled():
            return
        failed = task.exception()
        if failed is not None and not is_cancellation(failed):
            logger.warning("%s: %s failed", self.what, task.get_name(), exc_info=failed)
