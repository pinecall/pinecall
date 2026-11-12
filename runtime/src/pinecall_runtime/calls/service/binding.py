"""A call handed to a socket: call.attached, then its pump; parked calls given to the next one."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Iterable

from pinecall_runtime.agents.service import registry as agents_registry
from pinecall_runtime.calls.reducer import reduce, unanswered_tools
from pinecall_runtime.calls.service.live import OPENER_SILENT_S, Live, Served
from pinecall_runtime.calls.service.peers import HANDOFF_CHANNEL, Handoff, Unbound, heard_handoff, tell_handoff
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.loops import survived
from pinecall_runtime.postgres import box_task
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import CallAttached, CallStarted

logger = logging.getLogger(__name__)

# Entries a taking-over socket is rebuilt from; the prompt is not, the log keeps its hash alone.
STARTED = "call.started"
CLAIMED = "call.claimed"

# How long the listener waits for the signal before listening again, and how long `start` waits for it
# to be asked at all: the signal answers or says it is down within two seconds.
HEARD_RETRY_S = 1.0
ASKED_WITHIN_S = 5.0
# How often the calls whose opener is gone are looked for: a caller is on the line, and each tool it calls waits.
ADOPTED_EVERY_S = 1.0


async def attach(live: Live, call: str, app: agents_registry.SocketId) -> Entry | None:
    """Give the call to this socket: call.attached first, then the tools still waiting."""
    served = live.attach(call, app)
    if served is None:
        return None
    entries = await served.log.whole()
    started = next((entry for entry in entries if entry.type == STARTED), None)
    if started is None:
        # Not started yet: the socket hears it from what comes next.
        live.pumped(call, after=entries[-1].seq if entries else 0)
        return None
    claimed = next((str(entry.data["code"]) for entry in reversed(entries) if entry.type == CLAIMED), None)
    data = CallAttached(
        app=app,
        started=CallStarted.model_validate(started.data),
        state=reduce(entries).app_state,
        seq=entries[-1].seq,
        claimed=claimed,
    )
    entry = await served.log.append("call.attached", data.dump())
    # After call.attached, so the result lands on the call id still awaited: read off the log,
    # since the worker may have asked them of another gateway.
    live.pumped(call, after=entry.seq - 1, then=unanswered_tools(entries))
    return entry


async def attach_parked(live: Live, scope: Scope, slug: str, app: agents_registry.SocketId) -> None:
    """Give every parked call of the agent in the scope to this socket."""
    for call in live.parked(scope, slug):
        served = live.calls.get(call)
        if served is not None and not await _is_over(served):
            await attach(live, call, app)


# A call is parked by the gateway that opened it, wherever its socket was held: the copies of it
# on other gateways only send what the log holds to the socket, and tell the opener when it leaves.
async def hand_on(
    live: Live, registry: agents_registry.AgentRegistry, calls: Iterable[str], *, left: agents_registry.SocketId
) -> tuple[int, int]:
    """Hand the calls a socket let go on; how many were handed and how many parked."""
    handed = parked = 0
    for call in calls:
        served = live.calls.get(call)
        if served is None or await _is_over(served):
            continue
        if served.opened_here:
            went = await _hand_on(live, registry, served)
        else:
            live.attach(call, None)
            tell_handoff(live.signal, Handoff(unbound=Unbound(call=call, app=left)))
            went = registry.serving(served.scope, served.agent, None) is not None
        if went:
            handed += 1
        else:
            parked += 1
    return handed, parked


# What a pass of the reaper does for the calls opened here: one bound to a socket that holds no
# agent any more is parked (the word of its leaving was lost on the signal, or the gateway that
# held the socket died), and every parked one goes to whoever would take a new call of its agent,
# which is what the socket that took the agent did on another gateway, if the signal told this one.
async def hand_parked(live: Live, registry: agents_registry.AgentRegistry) -> list[str]:
    """Park the calls whose socket is gone, then give each parked call to the socket that takes its agent; which."""
    for call, served in list(live.calls.items()):
        if (
            served.opened_here
            and served.app is not None
            and registry.on_socket(served.app, served.scope.env, served.agent) is None
        ):
            live.attach(call, None)
    handed: list[str] = []
    for served in live.parked_here():
        with survived("the handing on of a parked call", served.call):
            taking = registry.serving(served.scope, served.agent, None)
            if taking is not None and not await _is_over(served):
                await attach(live, served.call, taking.owner)
                handed.append(served.call)
    return handed


# A spoken call outlives the gateway that opened it: its worker goes on and reads its commands from
# another, which held it as a copy alone. So no socket that took its agent was handed it, its tools
# waited out their deadline, and after its opener was forgotten it held no seat of its org. The
# gateway its worker reads from adopts it. Two gateways that adopted one call, each deaf to the other
# for a moment, settle it when they hear each other: the one of the greater id leaves it.
async def adopt_orphans(live: Live, registry: agents_registry.AgentRegistry, now: float) -> list[str]:
    """Take as this gateway's the calls whose opener is gone and whose worker reads here; hand them on; which."""
    if now - live.heard_since < OPENER_SILENT_S:
        return []
    elsewhere = live.opened_elsewhere(now)
    mine = live.counted.id
    for call, served in list(live.calls.items()):
        if served.opened_here and served.running is None and elsewhere.get(call, mine) < mine:
            live.disown(call)
    adopted = [
        call
        for call in live.followed
        if call in live.calls and not live.calls[call].opened_here and call not in elsewhere
    ]
    for call in adopted:
        live.adopt(call)
    if adopted:
        await hand_parked(live, registry)
    return adopted


class Handoffs:
    """What the other gateways say of the sockets, one that took an agent, a call one let go; and a call one left."""

    def __init__(self, live: Live, registry: agents_registry.AgentRegistry) -> None:
        """Listening to nobody until `start`."""
        self.live = live
        self.registry = registry
        self._listening: asyncio.Task[None] | None = None
        self._adopting: asyncio.Task[None] | None = None
        self._asked = asyncio.Event()

    async def start(self) -> None:
        """Hear the handoffs of every gateway, this one's included, once the signal was asked for them; adopt."""
        self._listening = box_task(self._listen())
        self._adopting = box_task(self._adopt())
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._asked.wait(), ASKED_WITHIN_S)

    async def close(self) -> None:
        """Stop hearing and adopting."""
        tasks = [task for task in (self._listening, self._adopting) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _adopt(self) -> None:
        while True:
            with survived("the adopting of the calls whose gateway left"):
                for call in await adopt_orphans(self.live, self.registry, time.monotonic()):
                    logger.warning("adopted %s: the gateway that opened it is gone, and its worker reads here", call)
            await asyncio.sleep(ADOPTED_EVERY_S)

    async def _listen(self) -> None:
        while True:
            try:
                listener = await self.live.signal.subscribe(HANDOFF_CHANNEL)
            except ServiceUnavailable:
                self._asked.set()
                await asyncio.sleep(HEARD_RETRY_S)
                continue
            self._asked.set()
            try:
                async for data in listener:
                    await self._heard(data)
            finally:
                listener.close()
            await asyncio.sleep(HEARD_RETRY_S)

    # A message this gateway could not apply is said, with the call or the agent it was about, and the
    # next is heard: a task that died with it would leave every call it could have handed parked.
    async def _heard(self, data: bytes) -> None:
        with survived("reading a handoff of another gateway") as reading:
            message = heard_handoff(data)
        if reading.failed:
            return
        if message.taking is not None:
            taking = message.taking
            with survived("handing the parked calls to the socket that took their agent", taking.agent):
                await attach_parked(self.live, taking.scope, taking.agent, taking.app)
        if message.unbound is not None:
            unbound = message.unbound
            with survived("handing on a call its socket let go", unbound.call):
                await self._let_go(unbound)

    # Only if the call is still bound to the socket that left: one handed on since is not parked.
    async def _let_go(self, unbound: Unbound) -> None:
        served = self.live.calls.get(unbound.call)
        if served is None or not served.opened_here or served.app != unbound.app or await _is_over(served):
            return
        await _hand_on(self.live, self.registry, served)


# An ended call waits for its seal, which needs no socket.
async def _is_over(served: Served) -> bool:
    return (await served.log.snapshot()).status == "ended"


async def _hand_on(live: Live, registry: agents_registry.AgentRegistry, served: Served) -> bool:
    taking = registry.serving(served.scope, served.agent, None)
    if taking is not None and await attach(live, served.call, taking.owner) is not None:
        return True
    live.attach(served.call, None)
    return False
