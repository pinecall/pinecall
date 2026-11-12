"""The reaper: how long a reaped call lasted, which calls it ends, and which it lets go of."""

import time
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.calls import service as calls
from runtime.calls.context import CallContext, Route, new_call_id
from runtime.calls.log.store import Store
from runtime.calls.log.writer import Writer
from runtime.calls.repository.heads import Claim
from runtime.calls.repository.unsealed import Unsealed
from runtime.calls.service.openings import keep_opening
from runtime.enums import Channel, Direction, Env
from runtime.exceptions import UpstreamError
from runtime.kit.text import JsonObject
from runtime.live.parts import LiveParts
from runtime.live.served import Opening, Served
from runtime.live.service import openings, reaper
from runtime.providers.stage import Running
from runtime.session.call import Call
from runtime.session.session import Place
from runtime.session.text import text_session
from runtime.wire.metrics import ModelUsage
from tests.calls.factories import claim_call
from tests.conftest import Tenant, needs_the_database
from tests.fakes.acme import ACME
from tests.session.conftest import NOBODY, Box, Through, context_of

A_START: JsonObject = {
    "channel": "web",
    "direction": "inbound",
    "from": "web_1",
    "to": "clinica-norte",
    "caller": None,
    "started_at": 1.0,
}
# Past every patience the reaper has: the calls a pass is handed are quiet by then, whenever they last moved.
MUCH_LATER_S = reaper.A_THREAD_WAITS_S + reaper.QUIET_S


def orphan(started_at: float | None, last_at: float) -> Unsealed:
    """A quiet call the reaper found, started or not."""
    return Unsealed(
        call="call_x", agent="clinica-norte", started_at=started_at, last_at=last_at, channel=None, env=None
    )


def test_a_started_call_lasted_from_its_start_to_its_last_entry() -> None:
    assert reaper.duration_of(orphan(1_000.0, 1_153.5)) == 153.5
    assert reaper.duration_of(orphan(1_000.0, 990.0)) == 0.0


def test_a_call_that_never_started_lasted_nothing_not_every_second_since_1970() -> None:
    assert reaper.duration_of(orphan(None, 1_792_760_955.0)) == 0.0


def a_context(tenant: Tenant, call: str, agent: str) -> CallContext:
    """A sandbox call of the tenant's agent through the widget."""
    return CallContext(
        call=call,
        channel=Channel.web,
        direction=Direction.inbound,
        caller="web_1",
        route=Route(org=tenant.org, agent=agent, channel=Channel.web, env=Env.sandbox),
        today=date(2026, 10, 23),
    )


@needs_the_database
async def test_an_opening_nobody_joined_is_found_quiet_with_no_start(
    store: Store, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> None:
    await claim_call(store, call, agent, Claim(Scope(tenant.org, Env.sandbox)))
    async with sessions.begin() as session:
        await keep_opening(session, tenant.org, a_context(tenant, call, agent), Declaration(slug=agent))
    async with sessions() as session:
        quiet = await calls.list_quiet_spoken(session, time.time() + 60, limit=1_000_000)
    found = next(one for one in quiet if one.call == call)
    assert found.started_at is None
    assert reaper.duration_of(found) == 0.0


async def served_here(live: LiveParts, tenant: Tenant, call: str, agent: str, *, claimed: bool = True) -> Served:
    """A call of the tenant's sandbox this gateway serves, as the open of a worker's call serves it."""
    scope = Scope(tenant.org, Env.sandbox)
    if claimed:
        await claim_call(live.store, call, agent, Claim(scope))
    opening = Opening(a_context(tenant, call, agent), Declaration(slug=agent), scope, None)
    return openings.serve(live, opening, opened_here=True)


# K F5 and M B10 (2026-10-23): a call sealed by the gateway that did not open it is let go of here
# once its head says sealed, and erasing a call left it served, holding its org's seat.
@needs_the_database
async def test_a_call_sealed_or_erased_is_let_go_of_and_one_still_open_is_not(
    live: LiveParts, tenant: Tenant, agent: str
) -> None:
    named = {name: new_call_id() for name in ("open", "sealed", "erased")}
    for name, call in named.items():
        await served_here(live, tenant, call, agent, claimed=name != "erased")
    await live.store.seal(named["sealed"])
    assert sorted(live.calls.holding(tenant.org, Env.sandbox)) == sorted(named.values())
    assert await reaper.let_go(live, time.monotonic()) == sorted([named["sealed"], named["erased"]])
    assert [served.call for served in live.calls.list_served()] == [named["open"]]
    assert live.calls.holding(tenant.org, Env.sandbox) == [named["open"]]
    live.calls.close_call(named["open"])


# A call sealed here is let go by its own seal once its bookkeeping is done: while that runs, the app's
# late line must still find the call, to be refused and named.
@needs_the_database
async def test_a_call_this_gateway_is_still_sealing_is_left_to_its_seal(
    live: LiveParts, tenant: Tenant, call: str, agent: str
) -> None:
    served = await served_here(live, tenant, call, agent)
    await live.store.seal(call)
    async with served.sealing:
        assert await reaper.let_go(live, time.monotonic()) == []
        assert live.calls.find(call) is served
    assert await reaper.let_go(live, time.monotonic()) == [call]


# The database is every test's, and every gateway of the suite reaps what it finds quiet in it: a pass
# of this test's is handed its own calls, quiet by the hour it is told, and nobody else's.
def these(*quiet: Unsealed) -> reaper.ListQuiet:
    """What lists the quiet calls for a pass over these alone."""

    async def listed(session: AsyncSession, quiet_since: float, *, limit: int) -> list[Unsealed]:
        del session, quiet_since, limit
        return list(quiet)

    return listed


def unsealed(call: str, agent: str, channel: str | None = None) -> Unsealed:
    """A call the reaper found open in the sandbox, last heard of a moment ago."""
    now = time.time()
    started_at = None if channel is None else now
    return Unsealed(call=call, agent=agent, started_at=started_at, last_at=now, channel=channel, env=Env.sandbox)


# The pass reads the quiet calls oldest first: one it cannot end must not be the one that keeps every
# call behind it from being ended, pass after pass.
@needs_the_database
async def test_a_call_another_gateway_is_sealing_is_left_and_the_ones_behind_it_are_ended(
    live: LiveParts, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, agent: str
) -> None:
    taken, free = new_call_id(), new_call_id()
    for call in (taken, free):
        await claim_call(live.store, call, agent, Claim(Scope(tenant.org, Env.sandbox)))
    elsewhere = Store(sessions, Writer(sessions))
    assert await elsewhere.lease_seal(taken, 60.0)
    quiet = these(unsealed(taken, agent), unsealed(free, agent))
    ended = await reaper.reap(live, time.time() + MUCH_LATER_S, spoken=quiet, written=these())
    await elsewhere.release_seal(taken)
    assert ended == [free]
    assert await live.store.is_sealed(free) and not await live.store.is_sealed(taken)
    kinds = [entry.type for entry in await live.store.whole_of(free)]
    assert kinds == ["call.ended", "call.summary", "call.score"]
    (end,) = [entry.data for entry in await live.store.whole_of(free) if entry.type == "call.ended"]
    assert (end["reason"], end["ended_by"], end["duration_s"]) == ("drained", "platform", 0.0)


async def a_seal_that_breaks(usage: list[ModelUsage], outcome: str) -> None:
    """The gateway's seal of a written call, on a day it does not answer."""
    del usage, outcome
    raise UpstreamError("the gateway did not answer the seal")


# A written call whose session closed here and whose seal broke is nobody's: it is ended like one a
# restart left. A call a worker runs, or a session still open, is never the reaper's to end.
@needs_the_database
async def test_a_written_call_whose_session_closed_unsealed_is_reaped_and_one_that_runs_is_not(
    live: LiveParts, tenant: Tenant, agent: str
) -> None:
    named = {name: new_call_id() for name in ("closed", "open", "worker", "gone")}
    for name, call in named.items():
        if name == "gone":
            await claim_call(live.store, call, agent, Claim(Scope(tenant.org, Env.sandbox)))
            await live.store.write("entry", call, agent, "call.started", A_START)
            continue
        served = await served_here(live, tenant, call, agent)
        if name == "worker":
            await live.store.write("entry", call, agent, "call.started", A_START)
            continue
        # A written call runs here: its session writes its start itself. The one that closes hands
        # its end to a seal that breaks, so its log stays open with nothing left to end it.
        box = Box(served.log)
        platform = Through(box, sealing=a_seal_that_breaks) if name == "closed" else box
        running = text_session(Call(context_of(call), NOBODY, platform), Running(ACME, "a-key"), Place())
        await running.start()
        live.calls.run(served, running)
    closed = live.calls.find(named["closed"])
    assert closed is not None and closed.running is not None
    with pytest.raises(UpstreamError, match="did not answer the seal"):
        await closed.running.close()
    assert closed.running.closed and not await live.store.is_sealed(named["closed"])
    quiet = these(*(unsealed(call, agent, "web") for call in named.values()))
    ended = await reaper.reap(live, time.time() + MUCH_LATER_S, spoken=these(), written=quiet)
    assert ended == [named["closed"], named["gone"]]
    for name in ("open", "worker"):
        assert not await live.store.is_sealed(named[name])
    still_open = live.calls.find(named["open"])
    assert still_open is not None and still_open.running is not None
    await still_open.running.close()
    for call in named.values():
        live.calls.close_call(call)
