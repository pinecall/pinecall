"""A call handed to a socket: call.attached, then its pump; parked calls given to whoever takes their agent."""

import asyncio
import contextlib
from collections.abc import Iterable

from runtime.actor import Scope
from runtime.calls import folds
from runtime.kit.loops import survive
from runtime.live.holders import Holders
from runtime.live.peers import HANDOFFS
from runtime.live.served import Calls, Served
from runtime.live.sockets import SocketId
from runtime.scoping import box_task
from runtime.wire.base import Entry
from runtime.wire.events import CallAttached, CallStarted
from runtime.wire.signal import Handoff, Scoped, Taking, Unbound

# Entries a taking-over socket is rebuilt from; the prompt is not, the log keeps its hash alone.
STARTED = "call.started"
CLAIMED = "call.claimed"
ENDED = "ended"

# How long `start` waits for the signal to be asked for the handoffs at all: it answers or says it
# is down within two seconds.
ASKED_WITHIN_S = 5.0


async def attach(calls: Calls, call: str, app: SocketId) -> Entry | None:
    """Give the call to this socket: call.attached first, then the tools still waiting."""
    served = calls.bind(call, app)
    if served is None:
        return None
    entries = await served.log.privacy.open_all()
    started = next((entry for entry in entries if entry.type == STARTED), None)
    if started is None:
        # Not started yet: the socket hears it from what comes next.
        calls.start_pump(call, after=entries[-1].seq if entries else 0)
        return None
    claimed = next((str(entry.data["code"]) for entry in reversed(entries) if entry.type == CLAIMED), None)
    data = CallAttached(
        app=app,
        started=CallStarted.model_validate(started.data),
        state=folds.reduce(entries).app_state,
        seq=entries[-1].seq,
        claimed=claimed,
    )
    entry = await served.log.append("call.attached", data.dump())
    # After call.attached, so the result lands on the call id still awaited: read off the log,
    # since the worker may have asked them of another gateway.
    calls.start_pump(call, after=entry.seq - 1, then=folds.list_unanswered_tools(entries))
    return entry


async def attach_parked(calls: Calls, scope: Scope, slug: str, app: SocketId) -> None:
    """Give every parked call of the agent in the scope to this socket."""
    for served in calls.list_parked_of(scope, slug):
        if calls.find(served.call) is served and not await _is_over(served):
            await attach(calls, served.call, app)


# A socket that took an agent tells every gateway, this one included: the calls parked for it on the
# others are its to take too.
def tell_taking(calls: Calls, scope: Scope, slug: str, app: SocketId) -> None:
    """Tell every gateway that the socket took the agent in the scope."""
    told = Scoped(org=scope.org, env=scope.env, holder=scope.holder)
    HANDOFFS.tell(calls.signal, Handoff(taking=Taking(app=app, scope=told, agent=slug)))


# A call is parked by the gateway that opened it, wherever its socket was held: the copies of it
# on other gateways only send what the log holds to the socket, and tell the opener when it leaves.
async def hand_on(calls: Calls, holders: Holders, left: SocketId, leaving: Iterable[Served]) -> tuple[int, int]:
    """Hand the calls a socket let go on; how many were handed and how many parked."""
    handed = parked = 0
    for served in leaving:
        if calls.find(served.call) is not served or await _is_over(served):
            continue
        if served.opened_here:
            went = await _hand_on(calls, holders, served)
        else:
            calls.bind(served.call, None)
            # Lossy, as the signal is: a call whose notice was lost is handed on at the reaper's next pass.
            HANDOFFS.tell(calls.signal, Handoff(unbound=Unbound(call=served.call, app=left)))
            went = holders.find_serving(served.scope, served.agent) is not None
        if went:
            handed += 1
        else:
            parked += 1
    return handed, parked


# What a pass of the reaper does for the calls opened here: one bound to a socket that holds no
# agent any more is parked (the word of its leaving was lost on the signal, or the gateway that
# held the socket died), and every parked one goes to whoever would take a new call of its agent,
# which is what the socket that took the agent did on another gateway, if the signal told this one.
async def hand_parked(calls: Calls, holders: Holders) -> list[str]:
    """Park the calls whose socket is gone, then give each parked call to the socket that takes its agent; which."""
    for served in calls.list_served():
        if (
            served.opened_here
            and served.app is not None
            and holders.find_on_socket(served.app, served.scope.env, served.agent) is None
        ):
            calls.bind(served.call, None)
    handed: list[str] = []
    for served in calls.list_parked():
        with survive("the handing on of a parked call", served.call):
            taking = holders.find_serving(served.scope, served.agent)
            if taking is not None and not await _is_over(served):
                await attach(calls, served.call, taking.owner)
                handed.append(served.call)
    return handed


class Handoffs:
    """What the other gateways say of the sockets: one that took an agent, a call one let go."""

    def __init__(self, calls: Calls, holders: Holders) -> None:
        """Listening to nobody until `start`."""
        self._calls = calls
        self._holders = holders
        self._listening: asyncio.Task[None] | None = None
        self._asked = asyncio.Event()

    async def start(self) -> None:
        """Hear the handoffs of every gateway, this one's included, once the signal was asked for them."""
        self._listening = box_task(HANDOFFS.listen(self._calls.signal, self._hear, asked=self._asked))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._asked.wait(), ASKED_WITHIN_S)

    async def close(self) -> None:
        """Stop hearing."""
        if self._listening is not None:
            self._listening.cancel()
            await asyncio.gather(self._listening, return_exceptions=True)

    # A message this gateway could not apply is said, with the call or the agent it was about, and the
    # next is heard: a task that died with it would leave every call it could have handed parked.
    async def _hear(self, message: Handoff) -> None:
        if message.taking is not None:
            taking = message.taking
            scope = Scope(taking.scope.org, taking.scope.env, taking.scope.holder)
            with survive("handing the parked calls to the socket that took their agent", taking.agent):
                await attach_parked(self._calls, scope, taking.agent, taking.app)
        if message.unbound is not None:
            unbound = message.unbound
            with survive("handing on a call its socket let go", unbound.call):
                await self._let_go(unbound)

    # Only if the call is still bound to the socket that left: one handed on since is not parked.
    async def _let_go(self, unbound: Unbound) -> None:
        served = self._calls.find(unbound.call)
        if served is None or not served.opened_here or served.app != unbound.app or await _is_over(served):
            return
        await _hand_on(self._calls, self._holders, served)


# An ended call waits for its seal, which needs no socket.
async def _is_over(served: Served) -> bool:
    return (await served.log.snapshot()).status == ENDED


async def _hand_on(calls: Calls, holders: Holders, served: Served) -> bool:
    taking = holders.find_serving(served.scope, served.agent)
    if taking is not None and await attach(calls, served.call, taking.owner) is not None:
        return True
    calls.bind(served.call, None)
    return False
