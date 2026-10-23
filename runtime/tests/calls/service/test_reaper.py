"""The reaper: how long a reaped call lasted, which calls it seals, and which it lets go of."""

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.calls.logs import Log, Logs
from pinecall_runtime.calls.repository.heads import Claim, HeadRepository, Unsealed
from pinecall_runtime.calls.repository.openings import OpeningRepository
from pinecall_runtime.calls.service import reaper
from pinecall_runtime.calls.service.live import Live, Served
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.calls.service.tool_calls import ToolCalls
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.session import service as session
from tests.conftest import Tenant, needs_the_database
from tests.session.conftest import context_of


def orphan(started_at: float | None, last_at: float) -> Unsealed:
    """A quiet call the reaper found, started or not."""
    return Unsealed(
        call="call_x", agent="clinica-norte", started_at=started_at, last_at=last_at, channel=None, env=None
    )


def test_a_started_call_lasted_from_its_start_to_its_last_entry() -> None:
    assert reaper.lasted(orphan(1_000.0, 1_153.5)) == 153.5
    assert reaper.lasted(orphan(1_000.0, 990.0)) == 0.0


def test_a_call_that_never_started_lasted_nothing_not_every_second_since_1970() -> None:
    assert reaper.lasted(orphan(None, 1_792_760_955.0)) == 0.0


@needs_the_database
async def test_an_opening_nobody_joined_is_found_quiet_with_no_start(
    store: Store, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, call: str, agent: str
) -> None:
    await store.claim(call, agent, tenant.org, Claim(Scope(tenant.org, Env.sandbox)))
    async with sessions.begin() as session:
        await OpeningRepository(session).keep(call, tenant.org, {}, "hash")
    async with sessions() as session:
        quiet = await HeadRepository(session).unsealed_spoken(time.time() + 60, limit=1_000)
    found = next(one for one in quiet if one.call == call)
    assert found.started_at is None
    assert reaper.lasted(found) == 0.0


async def nothing_before(_call_id: str) -> None:
    return None


def served_here(live: Live, store: Store, call: str, agent: str, running: object = None) -> None:
    """A call this gateway serves: a worker's when it runs no session here, a written one's when it does."""
    log = Log(store, call, agent)
    config = AgentConfig(slug=agent)
    live.serve(
        Served(
            agent=agent,
            scope=Scope("org_1", Env.sandbox),
            app=None,
            log=log,
            commands=asyncio.Queue(),
            context=context_of(call, Channel.web),
            config=config,
            tools=ToolCalls(config, log, nothing_before, nothing_before),
            running=cast(session.Session | None, running),
        )
    )


# K F5 and M B10 (2026-10-23): a call sealed by the gateway that did not open it is let go of here
# once its head says sealed, and erasing a call left it in Live.calls, holding its org's seat.
@needs_the_database
async def test_a_call_sealed_or_erased_is_let_go_of_and_one_still_open_is_not(
    store: Store, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, agent: str
) -> None:
    live = Live()
    serving = cast(Serving, SimpleNamespace(live=live, logs=Logs(store), handles=SimpleNamespace(sessions=sessions)))
    calls = {name: f"CA_{name}_{agent[-6:]}" for name in ("open", "sealed", "erased")}
    for name, call in calls.items():
        served_here(live, store, call, agent)
        if name != "erased":
            await store.claim(call, agent, tenant.org, Claim(Scope(tenant.org, Env.sandbox)))
    await store.seal(calls["sealed"])
    assert live.running("org_1", Env.sandbox) == 3
    assert await reaper.let_go(serving, time.monotonic()) == sorted([calls["sealed"], calls["erased"]])
    assert list(live.calls) == [calls["open"]]
    assert live.running("org_1", Env.sandbox) == 1
    live.close_call(calls["open"])


def unsealed(call: str, last_at: float, channel: str | None = None) -> Unsealed:
    """A call the reaper found open, started a moment before its last entry."""
    return Unsealed(call=call, agent="clinica-norte", started_at=1.0, last_at=last_at, channel=channel, env=None)


class Quiet:
    """What the reaper reads of the heads, and what it is asked to finish, with no database."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, spoken: list[Unsealed], written: list[Unsealed]) -> None:
        """Found as given; every call is sealed but the ones named in `breaks`."""
        self.tried: list[str] = []
        self.breaks: set[str] = set()

        async def read_spoken(_heads: HeadRepository, _since: float, *, limit: int) -> list[Unsealed]:
            return spoken

        async def read_written(_heads: HeadRepository, _since: float, *, limit: int) -> list[Unsealed]:
            return written

        async def finish(_serving: Serving, orphan: Unsealed, _reason: str) -> bool:
            self.tried.append(orphan.call)
            if orphan.call in self.breaks:
                raise ValueError("1 validation error for CallStarted: caller is required")
            return True

        @asynccontextmanager
        async def opened() -> AsyncGenerator[None]:
            yield None

        self.opened = opened
        monkeypatch.setattr(HeadRepository, "unsealed_spoken", read_spoken)
        monkeypatch.setattr(HeadRepository, "unsealed_written", read_written)
        monkeypatch.setattr(reaper, "_finish", finish)

    def serving(self, live: Live) -> Serving:
        """A gateway whose only job here is to hold its calls and be asked to reap."""
        return cast(Serving, SimpleNamespace(live=live, handles=SimpleNamespace(servers={}, sessions=self.opened)))


# The pass reads the quiet calls oldest first: one it cannot seal must not be the one that keeps
# every call behind it from being sealed, pass after pass.
async def test_a_call_the_reaper_cannot_seal_is_left_and_the_ones_behind_it_are_sealed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiet = Quiet(monkeypatch, [unsealed("call_bad", 2.0), unsealed("call_good", 3.0)], [])
    quiet.breaks.add("call_bad")
    assert await reaper.reap(quiet.serving(Live()), 10_000.0) == ["call_good"]
    assert quiet.tried == ["call_bad", "call_good"]


# A written call whose session closed here and whose seal broke is nobody's: it is sealed like one
# a restart left. A call a worker runs, or a session still open, is never the reaper's to seal.
async def test_a_written_call_whose_session_closed_unsealed_is_reaped_and_one_that_runs_is_not(
    monkeypatch: pytest.MonkeyPatch, store: Store, agent: str
) -> None:
    live = Live()
    named = {"closed": "call_closed", "open": "call_open", "worker": "call_worker", "gone": "call_gone"}
    served_here(live, store, named["closed"], agent, SimpleNamespace(closed=True))
    served_here(live, store, named["open"], agent, SimpleNamespace(closed=False))
    served_here(live, store, named["worker"], agent)
    quiet = Quiet(monkeypatch, [], [unsealed(call, 2.0, "web") for call in named.values()])
    assert await reaper.reap(quiet.serving(live), 10_000.0) == [named["closed"], named["gone"]]
    for call in (named["closed"], named["open"], named["worker"]):
        live.close_call(call)


# A call sealed here is let go by its own seal once its bookkeeping is done: while that runs, the app's late
# line must still find the call, to be refused and named.
@needs_the_database
async def test_a_call_this_gateway_is_still_sealing_is_left_to_its_seal(
    store: Store, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, agent: str
) -> None:
    live = Live()
    serving = cast(Serving, SimpleNamespace(live=live, logs=Logs(store), handles=SimpleNamespace(sessions=sessions)))
    call = f"CA_sealing_{agent[-6:]}"
    served_here(live, store, call, agent)
    await store.claim(call, agent, tenant.org, Claim(Scope(tenant.org, Env.sandbox)))
    await store.seal(call)
    async with live.calls[call].sealing:
        assert await reaper.let_go(serving, time.monotonic()) == []
        assert call in live.calls
    assert await reaper.let_go(serving, time.monotonic()) == [call]
