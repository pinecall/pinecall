"""A call handed to a socket: call.attached, then its pump; parked calls given to the next one."""

from collections.abc import Iterable

from pinecall_runtime.agents.service import registry as agents_registry
from pinecall_runtime.calls.reducer import reduce, unanswered_tools
from pinecall_runtime.calls.service.live import Live
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import CallAttached, CallStarted

# Entries a taking-over socket is rebuilt from; the prompt is not, the log keeps its hash alone.
STARTED = "call.started"
CLAIMED = "call.claimed"


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
        await attach(live, call, app)


# Each call of a leaving socket goes where a new call would, or waits parked.
async def hand_on(live: Live, registry: agents_registry.AgentRegistry, calls: Iterable[str]) -> tuple[int, int]:
    """Hand the calls on; how many were handed and how many parked."""
    handed = parked = 0
    for call in calls:
        served = live.calls.get(call)
        # An ended call waits for its seal, which needs no socket.
        if served is None or (await served.log.snapshot()).status == "ended":
            continue
        taking = registry.serving(served.scope, served.agent, None)
        if taking is not None and await attach(live, call, taking.owner) is not None:
            handed += 1
        else:
            live.attach(call, None)
            parked += 1
    return handed, parked
