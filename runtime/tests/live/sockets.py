"""An app's socket open on a gateway, for the live side's tests: what it was sent, as the calls sent it."""

import time

from runtime.actor import Scope
from runtime.live.parts import LiveParts
from runtime.wire.base import Entry
from runtime.wire.signal import Scoped, SocketRow


class Heard:
    """An app's socket open on the gateway: every entry sent down it."""

    def __init__(self) -> None:
        self.sent: list[Entry] = []

    async def send(self, entry: Entry) -> None:
        """One entry down the socket."""
        self.sent.append(entry)

    async def stop(self, why: str) -> None:
        """The app was stopped."""

    async def kill(self, slug: str, why: str) -> None:
        """One of its agents was killed."""

    def of(self, kind: str) -> list[Entry]:
        """The entries of this kind it was sent."""
        return [entry for entry in self.sent if entry.type == kind]


def an_app(live: LiveParts, app: str, scope: Scope) -> Heard:
    """An app's socket connected to the gateway under this id, in the scope."""
    socket = Heard()
    told = Scoped(org=scope.org, env=scope.env, holder=scope.holder)
    live.sockets.connect(SocketRow(app=app, scope=told, address=None, connected_at=time.time()), socket)
    return socket
