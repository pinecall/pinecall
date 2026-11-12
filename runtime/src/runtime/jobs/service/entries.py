"""A call's batches down one socket to the gateway, each answered with the seqs the log gave them."""

import asyncio
import json
from collections.abc import Mapping, Sequence

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from runtime.exceptions import UpstreamError
from runtime.jobs.service.client import TIMEOUT_S, unavailable
from runtime.kit.text import a_mapping
from runtime.kit.websockets import A_REFUSAL
from runtime.wire.base import BatchedEntry, Entry
from runtime.wire.worker import AppendEntriesRefused, AppendEntriesRequest, AppendEntriesResponse

# The close codes the gateway refuses a socket with: 4000 plus the status a request would get.
REFUSALS = range(A_REFUSAL, A_REFUSAL + 1000)


# One batch is out at a time (the call's writer sends the next when this one is answered), so an
# answer is the last frame sent. An answer that does not come within the request's timeout is
# not waited for past it: the socket is dropped, and the retry asks again on a new one.
class EntriesStream:
    """A call's batches down one WebSocket to the gateway, each answered with its seqs."""

    def __init__(self, url: str, headers: Mapping[str, str]) -> None:
        """Not connected yet: the first batch connects."""
        self.url = url
        self.headers = dict(headers)
        self.socket: ClientConnection | None = None
        self._sending = asyncio.Lock()

    async def append_many(self, entries: Sequence[BatchedEntry], *, after: int) -> list[Entry]:
        """Send the batch and read its answer; the gateway's failure when the socket or the log refused."""
        frame = AppendEntriesRequest(after=after, entries=list(entries)).dump_json()
        async with self._sending:
            socket = await self._connect()
            try:
                await socket.send(frame)
                raw = await asyncio.wait_for(socket.recv(), TIMEOUT_S)
            except (ConnectionClosed, OSError, TimeoutError) as lost:
                await self.close()
                raise self._failure_of(lost) from lost
        answer: object = json.loads(raw)
        if a_mapping(answer) and "refused" in answer:
            refused = AppendEntriesRefused.model_validate(answer)
            raise unavailable(f"WS {self.url}: {refused.status} {refused.refused}", answered=refused.status)
        return AppendEntriesResponse.model_validate(answer).entries

    async def close(self) -> None:
        """Close the socket; the next batch opens another."""
        socket, self.socket = self.socket, None
        if socket is not None:
            await socket.close()

    async def _connect(self) -> ClientConnection:
        if self.socket is not None:
            return self.socket
        try:
            self.socket = await connect(self.url, additional_headers=self.headers, open_timeout=TIMEOUT_S)
        except InvalidStatus as refused:
            # Answered before the handshake: a key the gateway does not take is an answer, not an absence.
            status = refused.response.status_code
            raise unavailable(f"WS {self.url}: {status}", answered=status) from refused
        except (InvalidHandshake, OSError, TimeoutError) as unreachable:
            raise unavailable(f"WS {self.url}: {unreachable}") from unreachable
        return self.socket

    # The gateway accepts a socket it refuses and closes it with the status as its code (a refusal
    # before the handshake is a bare 403): a call it forgot reads here as the 404 it is, as on a request.
    def _failure_of(self, lost: Exception) -> UpstreamError:
        closed = lost.rcvd if isinstance(lost, ConnectionClosed) else None
        if closed is not None and closed.code in REFUSALS:
            return unavailable(f"WS {self.url}: {closed.reason}", answered=closed.code - A_REFUSAL)
        return unavailable(f"WS {self.url}: {lost}")
