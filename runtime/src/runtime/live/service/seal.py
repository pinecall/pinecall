"""The end of a call, once: the lease one gateway seals it under, and the order its end runs in."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator

from runtime.calls.log import Store
from runtime.exceptions import Conflict, ServiceUnavailable
from runtime.kit.loops import survive
from runtime.live.parts import LiveParts
from runtime.live.served import Served
from runtime.live.service import ending
from runtime.live.service.ending import Closing, Sealing
from runtime.wire.base import Entry
from runtime.wire.scores import CallScore

logger = logging.getLogger(__name__)

# How long one gateway holds the right to seal a call, renewed at a third of it while it seals:
# a gateway that dies sealing lets the call go within these seconds, and a request waiting on it
# takes the seal over. Held 120 s unrenewed, a worker gave up (30 s) on a call whose sealing
# gateway died, and the reaper sealed it later with no usage: measured with a gateway killed
# every minute.
LEASED_S = 15.0
LOOKED_AGAIN_S = 0.5
# How long a request waits on another gateway's seal before it says so: the worker asks again.
WAITED_AT_MOST_S = 25.0


class SealedElsewhere(ServiceUnavailable):
    """Another gateway is sealing the call and has not finished."""

    def __init__(self, call: str) -> None:
        super().__init__(f"call {call} is being sealed by another gateway, which has not finished: ask again")


# One end for every call: a worker's, a written one's, and one the platform ends for nobody
# (`end_unserved`). A call is sealed once: a second request waits for the first and finds the call
# gone, and a seal that broke after its summary goes on from the score, so no call is remembered or
# billed twice. Across gateways the head's lease does what the lock does here: a request that finds
# it taken waits for the log to say sealed.
async def seal_call(live: LiveParts, served: Served, sealing: Sealing) -> None:
    """Remember, price the call, write its summary and its score, seal the log, let it go."""
    async with served.sealing:
        if live.calls.find(served.call) is not served:
            return
        if not await live.store.lease_seal(served.call, LEASED_S) and await _wait_for_the_other(live, served):
            return
        closing = ending.closing_of(served, sealing)
        entries, judged = await _seal(live, closing, served)
        # The score sealed the log: the call is over whatever its bookkeeping after it does, and a call
        # left served here counts against its org's calls at once until the process restarts.
        try:
            await _follow(live, closing, entries, judged)
        finally:
            live.logs.forget(served.call)
            live.calls.close_call(served.call)


# The same end, for a call no session and no worker is left to end: one the reaper found quiet, a
# dial the media plane refused. Until 2026-11 each wrote an end of its own (the reaper's with no
# drift, no case and no alert, the dial's with no summary and no score), and a day's numbers moved
# when a rebuild counted what the live path had not.
async def end_unserved(live: LiveParts, call: str, agent: str, sealing: Sealing) -> bool:
    """End a call nothing serves: its end, its summary and its score written, its log sealed; False if another did."""
    if not await live.store.lease_seal(call, LEASED_S):
        return False
    log = live.logs.writing(call, agent)
    try:
        closing = await ending.closing_of_unserved(live, call, agent, log, sealing)
        entries, judged = await _seal(live, closing, None)
        await _follow(live, closing, entries, judged)
    except Conflict:
        # Another gateway sealed it first: nothing is left to do.
        return False
    finally:
        live.logs.forget(call)
    live.calls.close_call(call)
    return True


# The order of an end, read top to bottom. The log is read once and each step adds what it writes:
# until 2026-11 it was read from Postgres five times over one seal.
async def _seal(live: LiveParts, closing: Closing, served: Served | None) -> tuple[list[Entry], CallScore]:
    store, call = live.store, closing.call
    try:
        async with _hold_lease(store, call):
            entries = await store.whole_of(call)
            await ending.write_end(closing, entries)
            if all(entry.type != "call.summary" for entry in entries):
                written = await ending.remember(live, closing, entries)
                await ending.price(live, closing, entries, written)
            judged = await ending.score(live, closing, entries)
            if served is not None:
                await ending.wait_for_the_app(live, served)
            entries.append(await closing.log.append("call.score", judged.dump()))
    except BaseException:
        await store.release_seal(call)
        raise
    return entries, judged


async def _follow(live: LiveParts, closing: Closing, entries: list[Entry], judged: CallScore) -> None:
    for what, step in ending.AFTER_SEAL:
        with survive(what, closing.call):
            await step(live, closing, entries, judged)


# True once another gateway sealed it; False when its lease ran out (that gateway died sealing)
# and this one took it over, so the caller seals.
async def _wait_for_the_other(live: LiveParts, served: Served) -> bool:
    store = live.store
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAITED_AT_MOST_S
    while not await store.is_sealed(served.call):
        if await store.lease_seal(served.call, LEASED_S):
            return False
        if loop.time() > deadline:
            raise SealedElsewhere(served.call)
        await asyncio.sleep(LOOKED_AGAIN_S)
    live.logs.forget(served.call)
    live.calls.close_call(served.call)
    return True


# Held for as long as the seal runs, and no longer: the renewals end when the seal says it is done.
@contextlib.asynccontextmanager
async def _hold_lease(store: Store, call: str) -> AsyncGenerator[None]:
    done = asyncio.Event()
    renewing = asyncio.create_task(_renew(store, call, done))
    try:
        yield
    finally:
        done.set()
        await asyncio.gather(renewing, return_exceptions=True)


async def _renew(store: Store, call: str, done: asyncio.Event) -> None:
    while not done.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(done.wait(), LEASED_S / 3)
        if done.is_set():
            return
        # A renewal that failed is said and tried again a third of the lease on: the loop that ended
        # on it would let the lease lapse under a seal still running, and another gateway take it.
        with survive("renewing a seal's lease", call):
            await store.renew_seal(call, LEASED_S)
