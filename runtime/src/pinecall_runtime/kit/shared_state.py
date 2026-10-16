"""State each gateway holds a share of, told to the others on the signal and merged by each."""

import asyncio
import contextlib
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter

from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.postgres import box_task
from pinecall_runtime.redis import Signal

# Each process says its whole share this often, and forgets another's once silent this long.
TOLD_EVERY_S = 10.0
SILENT_AT_MOST_S = 30.0
RETRY_S = 1.0
# A key set to nobody is kept this long, so an older setting another process still says stays out.
FORGOTTEN_AFTER_S = 60.0


class Said(BaseModel):
    """One message on a share's channel: which process said it, and its share whole."""

    sender: str
    share: object


@dataclass(frozen=True, slots=True)
class Assigned:
    """A key of an env as one process last set it: to a holder, or to nobody, and when."""

    env: str
    key: str
    holder: str | None
    at: float


@dataclass(slots=True)
class Heard[T]:
    """Another process's share, and when it last said it."""

    share: T
    at: float


# Lossy by design: every share is said whole, again and again, so a lost message costs one beat.
# What a share holds must be small: it travels whole every TOLD_EVERY_S.
class SharedState[T]:
    """One share of this process, the others' as last heard, and a callback when either moves."""

    def __init__(
        self,
        signal: Signal,
        channel: str,
        adapter: TypeAdapter[T],
        empty: T,
        on_change: Callable[[], None],
    ) -> None:
        self.signal = signal
        self.channel = channel
        self.id = uuid4().hex
        self.every_s = TOLD_EVERY_S
        self.mine = empty
        # Set by an owner whose share changes too often to put: read as it is said.
        self.gathered: Callable[[], T] | None = None
        self.theirs: dict[str, Heard[T]] = {}
        self._adapter = adapter
        self._on_change = on_change
        self._tasks: list[asyncio.Task[None]] = []

    def put(self, share: T) -> None:
        """This process's share changed: keep it and say it at once."""
        self.mine = share
        self._say()

    async def start(self) -> None:
        """Listen to the others and say this share every beat."""
        self._tasks = [box_task(self._listen()), box_task(self._beat())]

    async def close(self) -> None:
        """Stop listening and saying."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def _say(self) -> None:
        mine = self.mine if self.gathered is None else self.gathered()
        message = Said(sender=self.id, share=self._adapter.dump_python(mine, mode="json"))
        self.signal.publish(self.channel, message.model_dump_json().encode())

    async def _beat(self) -> None:
        while True:
            self._say()
            await asyncio.sleep(self.every_s)
            now = time.monotonic()
            silent = [gw for gw, heard in self.theirs.items() if now - heard.at > SILENT_AT_MOST_S]
            for gateway in silent:
                del self.theirs[gateway]
            if silent:
                self._on_change()

    async def _listen(self) -> None:
        while True:
            try:
                listener = await self.signal.subscribe(self.channel)
            except ServiceUnavailable:
                await asyncio.sleep(RETRY_S)
                continue
            self._say()
            try:
                async for data in listener:
                    self._hear(data)
            finally:
                listener.close()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.signal.connected(), RETRY_S)

    def _hear(self, data: bytes) -> None:
        message = Said.model_validate_json(data)
        if message.sender == self.id:
            return
        new = message.sender not in self.theirs
        share = self._adapter.validate_python(message.share)
        self.theirs[message.sender] = Heard(share, time.monotonic())
        self._on_change()
        if new:
            self._say()


def newest(mine: dict[tuple[str, str], Assigned], theirs: Iterable[Assigned]) -> dict[tuple[str, str], str]:
    """Each key's holder by its newest setting, ours and theirs; ours pruned of what is spent."""
    latest = dict(mine)
    for assigned in theirs:
        key = (assigned.env, assigned.key)
        if key not in latest or latest[key].at < assigned.at:
            latest[key] = assigned
    now = time.time()
    for key, kept in list(mine.items()):
        if latest[key] is not kept or (kept.holder is None and now - kept.at > FORGOTTEN_AFTER_S):
            del mine[key]
    return {key: setting.holder for key, setting in latest.items() if setting.holder is not None}
