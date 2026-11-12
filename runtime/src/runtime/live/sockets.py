"""The app sockets open on this gateway and on the others: each one's inbox, a word sent down one, the dev asks."""

import asyncio
from typing import Protocol

from runtime.enums import Env
from runtime.live.peers import APP_INBOX, DEV_ANSWERS, SOCKETS_CHANNEL
from runtime.scoping import box_task
from runtime.shared_state import SharedState
from runtime.signal import Listener, Signal
from runtime.wire.base import Entry
from runtime.wire.commands import DevAnswer
from runtime.wire.signal import Bound, ForApp, Killed, SocketRow, SocketsShare

# Minted, never id(websocket): CPython reuses addresses, and the id travels back as `?app=`.
type SocketId = str


# What this registry needs of a socket open here; `live.service.socket.AppSocket` is the one that is.
class OpenSocket(Protocol):
    """An app's socket open on this gateway, as the others' words reach it."""

    async def send(self, entry: Entry) -> None:
        """One entry down the socket, as the log holds it."""
        ...

    async def stop(self, why: str) -> None:
        """Tell the app it was stopped, and close: it exits instead of reconnecting."""
        ...

    async def kill(self, slug: str, why: str) -> None:
        """Tell the app one of its agents was killed, and let go of it here."""
        ...


# Not durable on purpose: it says which sockets are open now; the log is the record. A socket is a
# row whichever gateway holds it: until 2026-11 one here carried two callables (its stop, its kill)
# and one elsewhere two closures made to look like them.
class Sockets:
    """The app sockets open now, here and on every other gateway, and the asks a console waits on."""

    def __init__(self, signal: Signal) -> None:
        """Nothing open; the other gateways' sockets told on the signal."""
        self.signal = signal
        self._open: dict[SocketId, OpenSocket] = {}
        self._rows: dict[SocketId, SocketRow] = {}
        self._shared = SharedState(
            signal,
            SOCKETS_CHANNEL,
            load=SocketsShare.model_validate,
            dump=_dump_rows,
            empty=SocketsShare(()),
            on_change=lambda: None,
        )
        # Each dev.request asked here: the future its endpoint waits on, and the task that listens
        # for its answer from the socket's gateway.
        self._asked: dict[str, asyncio.Future[DevAnswer]] = {}
        self._listening: dict[str, asyncio.Task[None]] = {}

    async def start(self) -> None:
        """Hear the other gateways' sockets, and say this one's."""
        await self._shared.start()

    async def close(self) -> None:
        """Stop hearing and saying."""
        await self._shared.close()

    # ── the sockets ──

    def connect(self, row: SocketRow, socket: OpenSocket) -> None:
        """An app socket opened: the org's list of apps shows it from now on."""
        self._open[row.app] = socket
        self._rows[row.app] = row
        self._say()

    def disconnect(self, app: SocketId) -> None:
        """An app socket closed; its calls go on until another socket takes them."""
        self._open.pop(app, None)
        self._rows.pop(app, None)
        self._say()

    def name(self, app: SocketId, host: str | None) -> None:
        """The machine the app said it runs on."""
        found = self._rows.get(app)
        if found is not None and host is not None:
            self._rows[app] = found.model_copy(update={"host": host})
            self._say()

    def count_here(self) -> int:
        """How many app sockets are open on this gateway."""
        return len(self._open)

    def is_here(self, app: SocketId) -> bool:
        """Whether the socket is open on this gateway."""
        return app in self._open

    def find_here(self, app: SocketId) -> OpenSocket | None:
        """The socket, when it is open on this gateway."""
        return self._open.get(app)

    def apps_of(self, org: str, env: Env) -> list[SocketRow]:
        """The org's sockets in the env on every gateway, oldest first."""
        theirs = (row for heard in self._shared.theirs.values() for row in heard.share.root)
        found = [row for row in (*self._rows.values(), *theirs) if row.scope.org == org and row.scope.env is env]
        return sorted(found, key=lambda row: row.connected_at)

    async def inbox(self, app: SocketId) -> Listener:
        """The socket's inbox on the signal: what other gateways send it, while it is open here."""
        return await APP_INBOX.subscribe(self.signal, app=app)

    # dev.request is never stored: it goes straight down the socket, wherever it is held.
    async def tell(self, app: SocketId, entry: Entry) -> bool:
        """Send an entry to one socket; False when no gateway holds it."""
        here = self._open.get(app)
        if here is None:
            return await APP_INBOX.reach(self.signal, ForApp(entry=entry), app=app)
        await here.send(entry)
        return True

    # Lossy, as the signal is: a bound call whose notice was lost is told again when its worker asks
    # a tool, and parked calls are handed on at every pass of the reaper.
    def tell_bound(self, app: SocketId, bound: Bound) -> None:
        """Tell the gateway holding the socket that the call is bound to it, from this seq."""
        APP_INBOX.tell(self.signal, ForApp(bound=bound), app=app)

    # Another gateway's socket is stopped through its inbox, as any word to it goes.
    async def stop(self, app: SocketId, why: str) -> None:
        """Tell the app it was stopped, on whichever gateway holds its socket."""
        here = self._open.get(app)
        if here is None:
            await APP_INBOX.reach(self.signal, ForApp(stop=why), app=app)
        else:
            await here.stop(why)

    async def kill(self, app: SocketId, agent: str, why: str) -> None:
        """Tell the app one of its agents was killed, on whichever gateway holds its socket."""
        here = self._open.get(app)
        if here is None:
            await APP_INBOX.reach(self.signal, ForApp(kill=Killed(agent=agent, why=why)), app=app)
        else:
            await here.kill(agent, why)

    # ── the dev asks ──

    # Answered here, by the socket's gateway on the signal, or given up on (the asker cancels it):
    # the ask is forgotten whole whichever way it ends. Until 2026-11 an answer that came from another
    # gateway left the future, and the whole result of an eval with it, kept for the life of the process.
    async def ask(self, ask_id: str) -> asyncio.Future[DevAnswer]:
        """A future for the answer to a dev.request, answered here or by the socket's gateway."""
        answer: asyncio.Future[DevAnswer] = asyncio.get_running_loop().create_future()
        heard = asyncio.Event()
        listening = box_task(self._hear_answer(ask_id, answer, heard))
        self._asked[ask_id] = answer
        self._listening[ask_id] = listening

        def forget(_: asyncio.Future[DevAnswer]) -> None:
            self._asked.pop(ask_id, None)
            self._listening.pop(ask_id, None)
            listening.cancel()

        answer.add_done_callback(forget)
        await heard.wait()
        return answer

    async def answer_dev(self, answer: DevAnswer) -> bool:
        """Hand an app's dev.answer to the endpoint waiting for it; False when nobody waits."""
        waiting = self._asked.get(answer.id)
        if waiting is None:
            return await DEV_ANSWERS.reach(self.signal, answer, id=answer.id)
        if waiting.done():
            return False
        waiting.set_result(answer)
        return True

    # ── private ──

    async def _hear_answer(self, ask_id: str, answer: asyncio.Future[DevAnswer], heard: asyncio.Event) -> None:
        async def take(told: DevAnswer) -> None:
            if not answer.done():
                answer.set_result(told)

        await DEV_ANSWERS.listen(self.signal, take, asked=heard, id=ask_id)

    def _say(self) -> None:
        self._shared.put(SocketsShare(tuple(self._rows.values())))


def _dump_rows(share: SocketsShare) -> object:
    return share.model_dump(mode="json")
