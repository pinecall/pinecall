"""The agents a process holds, and leaving: a drain, then the socket closed, once."""

import asyncio

from pinecall.bridge import Mounted
from pinecall.client import Client, Drained


class Held:
    """What `hold` and `serve start` hold: the client, and the agents mounted on it."""

    def __init__(self, client: Client, mounted: list[Mounted]) -> None:
        """The client and its mounted agents."""
        self.client = client
        self.mounted = mounted
        self._drained: Drained | None = None
        self._closed = asyncio.Event()
        self._lock = asyncio.Lock()

    async def stop(self) -> Drained:
        """Drain every agent, then close the socket; asked twice, the first answer again."""
        async with self._lock:
            if self._drained is None:
                self._drained = await self.client.drain()
                await self.close()
            return self._drained

    async def close(self) -> None:
        """Close without draining: a second signal, or a stop the org already made."""
        await self.client.close()
        self._closed.set()

    async def closed(self) -> None:
        """Return once the socket is closed for good."""
        await self._closed.wait()
