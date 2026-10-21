"""The log in Postgres: contiguous seqs, batches taken once, the seal, the pages, the owners, the feed."""

import asyncio
import os
import signal
import sys
import textwrap
from collections.abc import Callable, Coroutine, Sequence

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pinecall_runtime.agents.declaration import Versions
from pinecall_runtime.calls.facts import line_of
from pinecall_runtime.calls.logs import Logs
from pinecall_runtime.calls.models import CallLogHead, log_name
from pinecall_runtime.calls.reducer import reduce
from pinecall_runtime.calls.repository.entries import Positioned
from pinecall_runtime.calls.repository.facts import FactsRepository
from pinecall_runtime.calls.repository.heads import Claim, Claimant
from pinecall_runtime.calls.schemas import DEFAULT_LIMIT
from pinecall_runtime.calls.service import lists
from pinecall_runtime.calls.store import Store
from pinecall_runtime.calls.writer import Unnumbered
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import Conflict, ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from tests.calls.factories import EXPECTED, GOLDEN
from tests.conftest import needs_the_database

pytestmark = needs_the_database


# `across` reads every log of the box, and other tests write theirs beside this one's.
def mine(rows: Sequence[Positioned], *calls: str) -> list[Positioned]:
    """The rows of these calls alone, in the order read."""
    return [row for row in rows if row.entry.call in calls]


# ── the writer's sessions ──


def test_the_writer_writes_on_the_sessions_of_its_own_when_it_is_given_them(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The gateway gives it a pool of its own, so an append never waits on a request for a connection."""
    shared = Store(sessions)
    assert shared.writer.sessions is sessions
    apart = async_sessionmaker(sessions.kw["bind"])
    assert Store(sessions, writing=apart).writer.sessions is apart


# ── seqs ──


async def test_the_first_entry_is_seq_one_and_each_append_hands_back_the_next(
    store: Store, call: str, agent: str
) -> None:
    ringing = await store.append(call, agent, "call.ringing", {"from": "+34600"}, ephemeral=False)
    started = await store.append(call, agent, "call.started", {}, ephemeral=False)
    assert (ringing.seq, started.seq) == (1, 2)
    assert await store.latest_seq(call) == 2


async def test_seqs_stay_contiguous_under_concurrent_appends(store: Store, call: str, agent: str) -> None:
    entries = await asyncio.gather(*(store.append(call, agent, "custom", {"n": n}, ephemeral=False) for n in range(50)))
    assert sorted(entry.seq for entry in entries) == list(range(1, 51))
    assert [entry.seq for entry in await store.since(call)] == list(range(1, 51))


async def test_an_ephemeral_takes_a_seq_and_leaves_a_hole_where_its_row_would_be(
    store: Store, call: str, agent: str
) -> None:
    await store.append(call, agent, "call.started", {}, ephemeral=False)
    interim = await store.append(call, agent, "user.transcript", {"text": "ho"}, ephemeral=True)
    await store.append(call, agent, "user.transcript", {"text": "hol"}, ephemeral=True)
    final = await store.append(call, agent, "turn.user", {"text": "hola"}, ephemeral=False)
    assert (interim.seq, interim.ephemeral, final.seq, final.ephemeral) == (2, True, 4, False)
    assert [entry.seq for entry in await store.since(call)] == [1, 4]
    assert await store.latest_seq(call) == 4


async def test_a_call_nobody_wrote_to_has_seq_zero_and_is_not_sealed(store: Store, call: str) -> None:
    assert await store.latest_seq(call) == 0
    assert not await store.is_sealed(call)
    assert await store.since(call) == []


async def test_the_store_hands_back_the_wires_envelope_stamped_by_its_clock(
    store: Store, call: str, agent: str
) -> None:
    entry = await store.append(call, agent, "call.started", {"channel": "phone"}, ephemeral=False)
    assert entry.dump() == {
        "seq": 1,
        "ts": 1.0,
        "call": call,
        "agent": agent,
        "type": "call.started",
        "ephemeral": False,
        "data": {"channel": "phone"},
    }
    assert await store.since(call) == [entry]


# ── a worker's batches ──


def batch_of(*types: str) -> list[Unnumbered]:
    return [
        Unnumbered(type=kind, data={"n": n}, ephemeral=kind == "user.transcript", ts=0.5)
        for n, kind in enumerate(types)
    ]


async def head_of(store: Store, call: str) -> CallLogHead:
    """The log's head row as it stands."""
    async with store.sessions() as session:
        head = await session.get(CallLogHead, call)
    assert head is not None, f"{call} has no head"
    return head


async def head_counts(store: Store, call: str) -> tuple[int, int, int | None]:
    """The head's seq, how many entries its worker wrote, and the seq of the last of them."""
    head = await head_of(store, call)
    return head.seq, head.written, head.written_seq


async def test_a_batch_takes_contiguous_seqs_and_its_rows_are_there(store: Store, call: str, agent: str) -> None:
    batch = await store.append_many(call, agent, batch_of("custom", "custom", "custom"), after=0)
    assert (batch.replayed, [entry.seq for entry in batch.entries]) == (False, [1, 2, 3])
    assert [(entry.seq, entry.data) for entry in await store.since(call)] == [
        (1, {"n": 0}),
        (2, {"n": 1}),
        (3, {"n": 2}),
    ]
    assert await head_counts(store, call) == (3, 3, 3)


async def test_the_same_batch_again_answers_the_same_seqs_and_writes_nothing(
    store: Store, call: str, agent: str
) -> None:
    first = await store.append_many(call, agent, batch_of("custom", "turn.user"), after=0)
    again = await store.append_many(call, agent, batch_of("custom", "turn.user"), after=0)
    assert again.replayed
    assert [entry.dump() for entry in again.entries] == [entry.dump() for entry in first.entries]
    assert [entry.seq for entry in await store.since(call)] == [1, 2]
    assert await head_counts(store, call) == (2, 2, 2)


async def test_a_batch_after_the_gateways_own_entry_counts_only_the_workers(
    store: Store, call: str, agent: str
) -> None:
    await store.append(call, agent, "call.ringing", {}, ephemeral=False)
    first = await store.append_many(call, agent, batch_of("custom", "custom"), after=0)
    await store.append(call, agent, "tool.call", {}, ephemeral=False)
    second = await store.append_many(call, agent, batch_of("custom"), after=2)
    assert [entry.seq for entry in [*first.entries, *second.entries]] == [2, 3, 5]
    assert await head_counts(store, call) == (5, 3, 5)
    replayed = await store.append_many(call, agent, batch_of("custom"), after=2)
    assert [entry.seq for entry in replayed.entries] == [5]
    assert [entry.seq for entry in await store.since(call)] == [1, 2, 3, 4, 5]


async def test_the_count_a_writer_resumes_from_is_the_heads_and_zero_for_a_new_log(
    store: Store, call: str, agent: str
) -> None:
    assert await store.taken_count(call) == 0
    await store.append(call, agent, "call.ringing", {}, ephemeral=False)
    await store.append_many(call, agent, batch_of("custom", "user.transcript"), after=0)
    await store.append(call, agent, "tool.call", {}, ephemeral=False)
    assert await store.taken_count(call) == 2


async def test_each_entry_keeps_its_own_time_bounded_by_the_clock_and_never_stepping_back(
    sessions: async_sessionmaker[AsyncSession], call: str, agent: str
) -> None:
    store = Store(sessions, clock=lambda: 10.0)
    times = [3.0, 2.0, 4.0, 12.0, 5.0]
    batch = [Unnumbered(type="custom", data={"n": n}, ephemeral=False, ts=ts) for n, ts in enumerate(times)]
    written = await store.append_many(call, agent, batch, after=0)
    assert [entry.ts for entry in written.entries] == [3.0, 3.0, 4.0, 10.0, 10.0]
    assert [entry.ts for entry in await store.since(call)] == [3.0, 3.0, 4.0, 10.0, 10.0]
    again = await store.append_many(call, agent, batch, after=0)
    assert [entry.dump() for entry in again.entries] == [entry.dump() for entry in written.entries]
    assert (await head_of(store, call)).started_at == 3.0
    await store.writer.drain()


async def test_a_batch_sent_twice_at_once_is_written_once_and_both_hear_the_same_seqs(
    store: Store, call: str, agent: str
) -> None:
    await store.append(call, agent, "call.ringing", {}, ephemeral=False)
    batch = batch_of("custom", "user.transcript", "custom")
    first, second = await asyncio.gather(
        store.append_many(call, agent, batch, after=0),
        store.append_many(call, agent, batch, after=0),
    )
    assert sorted([first.replayed, second.replayed]) == [False, True]
    assert [entry.seq for entry in first.entries] == [entry.seq for entry in second.entries]
    assert [entry.seq for entry in first.entries] == [2, 3, 4]
    assert [entry.seq for entry in await store.since(call)] == [1, 2, 4]
    assert await head_counts(store, call) == (4, 3, 4)


async def test_a_first_batch_that_says_something_came_before_it_is_refused(store: Store, call: str, agent: str) -> None:
    with pytest.raises(Conflict, match="took 0 entries from its worker"):
        await store.append_many(call, agent, batch_of("custom"), after=2)
    assert await store.latest_seq(call) == 0


@pytest.mark.parametrize(("after", "size"), [(3, 1), (0, 1), (1, 2), (0, 3)])
async def test_a_batch_that_is_neither_next_nor_the_last_again_is_refused_and_writes_nothing(
    store: Store, call: str, after: int, size: int, agent: str
) -> None:
    await store.append_many(call, agent, batch_of("custom", "custom"), after=0)
    with pytest.raises(Conflict, match="took 2 entries from its worker"):
        await store.append_many(call, agent, batch_of(*["custom"] * size), after=after)
    assert await head_counts(store, call) == (2, 2, 2)
    assert [entry.seq for entry in await store.since(call)] == [1, 2]


async def test_a_sealed_log_refuses_a_new_batch(store: Store, call: str, agent: str) -> None:
    await store.append_many(call, agent, batch_of("custom"), after=0)
    await store.seal(call)
    with pytest.raises(Conflict, match="has ended"):
        await store.append_many(call, agent, batch_of("custom"), after=1)
    assert await head_counts(store, call) == (1, 1, 1)


async def test_an_ephemeral_in_a_batch_takes_its_seq_and_no_row(store: Store, call: str, agent: str) -> None:
    batch = await store.append_many(call, agent, batch_of("user.transcript", "turn.user", "user.transcript"), after=0)
    assert [(entry.seq, entry.ephemeral) for entry in batch.entries] == [
        (1, True),
        (2, False),
        (3, True),
    ]
    assert [entry.seq for entry in await store.since(call)] == [2]
    assert await store.latest_seq(call) == 3


@pytest.mark.parametrize("size", [0, 257])
async def test_an_empty_batch_and_one_past_the_most_are_refused(store: Store, call: str, size: int, agent: str) -> None:
    with pytest.raises(ValidationError, match="1 to 256"):
        await store.append_many(call, agent, batch_of(*["custom"] * size), after=0)
    assert await store.latest_seq(call) == 0


# ── the first of its type ──


async def test_an_entry_of_a_type_the_log_lacks_is_written_and_a_second_is_not(
    store: Store, call: str, agent: str
) -> None:
    await store.append(call, agent, "call.started", {}, ephemeral=False)
    first = await store.append_first(call, agent, "call.ended", {"reason": "drained"})
    assert first is not None
    assert first.seq == 2
    assert await store.append_first(call, agent, "call.ended", {"reason": "error"}) is None
    assert [entry.type for entry in await store.since(call)] == ["call.started", "call.ended"]


async def test_two_writers_deciding_the_same_end_at_once_write_it_once(store: Store, call: str, agent: str) -> None:
    await store.append(call, agent, "call.started", {}, ephemeral=False)
    both = await asyncio.gather(*(store.append_first(call, agent, "call.ended", {"n": n}) for n in range(4)))
    assert sum(entry is not None for entry in both) == 1
    assert [entry.type for entry in await store.since(call)] == ["call.started", "call.ended"]


async def test_a_sealed_log_or_one_never_written_takes_no_first_entry(store: Store, call: str, agent: str) -> None:
    assert await store.append_first(call, agent, "call.ended", {}) is None
    assert await store.latest_seq(call) == 0
    await store.append(call, agent, "call.started", {}, ephemeral=False)
    await store.seal(call)
    assert await store.append_first(call, agent, "call.ended", {}) is None
    assert await store.latest_seq(call) == 1


# ── sealing ──


async def test_a_sealed_log_refuses_every_later_append_and_says_it_is_sealed(
    store: Store, call: str, agent: str
) -> None:
    await store.append(call, agent, "call.started", {}, ephemeral=False)
    await store.seal(call)
    with pytest.raises(Conflict, match="has ended"):
        await store.append(call, agent, "turn.user", {"text": "too late"}, ephemeral=False)
    await store.seal(call)
    assert await store.is_sealed(call)
    assert await store.latest_seq(call) == 1


async def test_a_log_can_be_sealed_before_anything_was_written_to_it(store: Store, call: str, agent: str) -> None:
    await store.seal(call)
    assert await store.is_sealed(call)
    with pytest.raises(Conflict, match="has ended"):
        await store.append(call, agent, "call.ringing", {}, ephemeral=False)


async def test_a_verdict_is_the_one_entry_a_sealed_log_still_takes(store: Store, call: str, agent: str) -> None:
    await store.append(call, agent, "call.summary", {"x": 1}, ephemeral=False)
    await store.seal(call)
    score = await store.rescore(call, agent, {"passed": True, "judges": [], "judge_calls": 1})
    assert (score.seq, score.type, score.ephemeral) == (2, "call.score", False)
    assert [entry.type for entry in await store.since(call)] == ["call.summary", "call.score"]
    with pytest.raises(Conflict, match="has no log to judge"):
        await store.rescore(f"{call}-nobody", agent, {})


# The line is what a list shows: written at the seal, so the list of a sealed call folds no log.
async def test_the_seal_writes_the_line_a_list_shows_and_the_list_reads_it_instead_of_folding(
    sessions: async_sessionmaker[AsyncSession], call: str
) -> None:
    """Before the seal the row is folded from the log; after it, read off the facts, and the same row but live."""
    ticks = iter(entry.ts for entry in GOLDEN)
    store = Store(sessions, clock=lambda: next(ticks))
    for entry in GOLDEN:
        await store.append(call, entry.agent, entry.type, entry.data, ephemeral=entry.ephemeral)
    await store.writer.drain()
    logs = Logs(store)
    async with sessions() as session:
        (folded,) = await lists.call_rows(session, logs, [call], {})
        before = await FactsRepository(session).get(call)
    assert before is not None and before.line is None
    await store.seal(call)
    async with sessions() as session:
        kept = await FactsRepository(session).get(call)
        (read,) = await lists.call_rows(session, logs, [call], {})
    state = reduce(await store.whole(call))
    assert kept is not None
    assert kept.line == line_of(state)
    assert folded.live and not read.live
    assert read.model_copy(update={"live": True}).dump() == folded.dump()
    assert (read.status, read.last_seq, read.caller) == ("ended", state.seq, state.caller)


# ── paging ──


async def test_since_never_returns_a_seq_at_or_below_the_cursor(store: Store, call: str, agent: str) -> None:
    for n in range(5):
        await store.append(call, agent, "custom", {"n": n}, ephemeral=False)
    for after in range(7):
        assert all(entry.seq > after for entry in await store.since(call, after=after))
    assert [entry.seq for entry in await store.since(call, after=3)] == [4, 5]


async def test_since_pages_in_seq_order_and_stops_at_the_limit(store: Store, call: str, agent: str) -> None:
    for n in range(5):
        await store.append(call, agent, "custom", {"n": n}, ephemeral=False)
    assert [entry.seq for entry in await store.since(call, after=1, limit=2)] == [2, 3]


async def test_whole_reads_every_page_and_starts_from_the_cursor(store: Store, call: str, agent: str) -> None:
    many = DEFAULT_LIMIT + 3
    await asyncio.gather(*(store.append(call, agent, "custom", {"n": n}, ephemeral=False) for n in range(many)))
    assert [entry.seq for entry in await store.whole(call)] == list(range(1, many + 1))
    assert [entry.seq for entry in await store.whole(call, after=many - 2)] == [many - 1, many]
    assert await store.whole(f"{call}-nobody") == []


# ── the agent's own log ──


async def test_the_agents_own_log_has_a_seq_of_its_own(store: Store, call: str, agent: str) -> None:
    registered = await store.append(None, agent, "agent.registered", {"routes": []}, ephemeral=False)
    ringing = await store.append(call, agent, "call.ringing", {}, ephemeral=False)
    configured = await store.append(None, agent, "agent.configured", {}, ephemeral=False)
    assert (registered.seq, ringing.seq, configured.seq) == (1, 1, 2)
    assert (registered.call, ringing.call) == (None, call)
    own = await store.since(log_name(None, agent))
    assert [entry.type for entry in own] == ["agent.registered", "agent.configured"]
    assert [entry.seq for entry in await store.since(log_name(None, agent), after=1)] == [2]


# ── owners ──


async def test_a_log_is_the_first_orgs_that_claims_it_and_never_moves(store: Store, call: str, agent: str) -> None:
    assert await store.claimant(call, agent) is None
    await store.claim(call, agent, "clinica")
    await store.claim(call, agent, "tienda")
    await store.append(call, agent, "call.started", {}, ephemeral=False)
    assert await store.claimant(call, agent) == Claimant("clinica", None)


async def test_a_claim_may_come_before_the_first_entry_and_carries_the_corner(
    store: Store, call: str, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    claim = Claim(Scope("clinica", Env.sandbox, "m_berna"), Versions(config=3, lexicon=1))
    await store.claim(call, agent, "clinica", claim)
    await store.claim(call, agent, "clinica", Claim(Scope("clinica"), Versions(config=9)))
    async with sessions() as session:
        head = await session.get(CallLogHead, call)
    assert head is not None
    assert (head.env, head.holder, head.config_version, head.lexicon_version) == ("sandbox", "m_berna", 3, 1)


async def test_the_agents_own_log_has_an_owner_of_its_own(store: Store, call: str, agent: str) -> None:
    await store.claim(None, agent, "clinica")
    assert await store.owner(agent) == "clinica"
    assert await store.claimant(call, agent) is None


async def test_a_logs_claimant_is_its_org_and_world_and_an_agents_log_has_no_world(
    store: Store, call: str, agent: str
) -> None:
    assert await store.claimant(call, agent) is None
    await store.claim(call, agent, "clinica", Claim(Scope("clinica", Env.sandbox)))
    await store.claim(None, agent, "clinica")
    assert await store.claimant(call, agent) == Claimant("clinica", Env.sandbox)
    assert await store.claimant(None, agent) == Claimant("clinica", None)


async def test_the_operator_moves_every_log_of_an_agent_to_another_org(
    store: Store, call: str, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await store.claim(call, agent, "wrong")
    await store.claim(None, agent, "wrong")
    async with sessions.begin() as session:
        assert await lists.move_logs(session, agent, "right") == 2
        assert await lists.move_logs(session, f"{agent}-nobody", "right") == 0
    assert await store.owner(agent) == "right"
    assert await store.claimant(call, agent) == Claimant("right", None)


# ── across every log ──


async def test_across_pages_the_metered_types_of_every_log_by_position(store: Store, call: str, agent: str) -> None:
    other = f"{call}-b"
    await store.claim(call, agent, "clinica")
    await store.claim(other, agent, "tienda")
    await store.append(call, agent, "call.started", {}, ephemeral=False)
    first = await store.append(call, agent, "call.summary", {"duration_s": 1}, ephemeral=False)
    await store.append(other, agent, "user.transcript", {"text": "hola"}, ephemeral=True)
    second = await store.append(other, agent, "call.summary", {"duration_s": 2}, ephemeral=False)
    rows = mine(await store.across(("call.summary",)), call, other)
    assert [(row.org, row.entry.seq) for row in rows] == [
        ("clinica", first.seq),
        ("tienda", second.seq),
    ]
    assert rows[0].position < rows[1].position
    resumed = mine(await store.across(("call.summary",), after=rows[0].position), call, other)
    assert [row.entry.call for row in resumed] == [other]
    assert mine(await store.across(("call.summary",), after=rows[1].position), call, other) == []


async def test_a_type_no_writer_orders_by_commit_is_not_read_across_every_log(store: Store) -> None:
    with pytest.raises(ValidationError, match=r"turn\.user"):
        await store.across(("call.summary", "turn.user"))


# ── the table itself ──


# ── the feed ──

# Who waits behind a backend: the one a row lock holds, then the one that one holds.
WAITING_ON = text("select pid from pg_stat_activity where :pid = any(pg_blocking_pids(pid))")
A_START: JsonObject = {
    "channel": "phone",
    "from": "+34600111222",
    "to": "+34910000000",
    "caller": None,
    "direction": "inbound",
    "started_at": 1.0,
    "persona": None,
}
A_SUMMARY: JsonObject = {"duration_s": 1}
FEEDS = ("call.summary", "call.score")


async def waiter_of(
    sessions: async_sessionmaker[AsyncSession], pid: int, done: Callable[[], bool] = lambda: False
) -> int | None:
    """A backend that waits on this one, once one does; None when `done` comes first."""
    async with asyncio.timeout(5):
        while not done():
            async with sessions() as session:
                waiting = (await session.execute(WAITING_ON, {"pid": pid})).scalars().first()
            if waiting is not None:
                return int(waiting)
            await asyncio.sleep(0.01)
    return None


# Each way a fed row is written: the gateway's entry, a worker's batch, a verdict on a sealed log.
async def fed_by_append(store: Store, call: str, agent: str) -> None:
    await store.append(call, agent, "call.summary", A_SUMMARY, ephemeral=False)


async def fed_by_batch(store: Store, call: str, agent: str) -> None:
    await store.append_many(call, agent, [Unnumbered("call.summary", A_SUMMARY, ephemeral=False, ts=1.0)], after=0)


# A verdict lands on a sealed log, and the seal itself writes the facts row (the line a list
# shows), so the log is sealed before the test holds that row.
async def fed_by_rescore(store: Store, call: str, agent: str) -> None:
    await store.rescore(call, agent, {"judges": [], "judge_calls": 0})


# The skip: a row numbered first and committed last, after a reader's cursor passed its number.
@pytest.mark.parametrize(
    ("fed", "sealed_first"), [(fed_by_append, False), (fed_by_batch, False), (fed_by_rescore, True)]
)
async def test_a_feed_read_by_cursor_never_passes_a_row_that_commits_late(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    store: Store,
    call: str,
    agent: str,
    fed: Callable[[Store, str, str], Coroutine[None, None, None]],
    sealed_first: bool,
) -> None:
    """A billing reader resuming from its cursor reads every fed row once, however late it commits."""
    early, late = f"{call}-early", f"{call}-late"
    for each in (early, late):
        await store.append(each, agent, "call.started", A_START, ephemeral=False)
    if sealed_first:
        await store.seal(early)
    async with engine.connect() as holder, holder.begin():
        # The early summary is numbered, then waits on its facts row before it can commit.
        await holder.execute(text("select 1 from call_facts where call = :call for update"), {"call": early})
        pid = (await holder.execute(text("select pg_backend_pid()"))).scalar_one()
        numbered_first = asyncio.create_task(fed(store, early, agent))
        blocked = await waiter_of(sessions, pid)
        assert blocked is not None
        # Another store is another gateway: a writer of its own, not queued behind this one.
        elsewhere = Store(sessions, clock=store.clock)
        numbered_last = asyncio.create_task(elsewhere.append(late, agent, "call.score", A_SUMMARY, ephemeral=False))
        await waiter_of(sessions, blocked, numbered_last.done)
        read_first = mine(await store.across(FEEDS), early, late)
    await numbered_first
    await numbered_last
    await elsewhere.writer.drain()
    cursor = read_first[-1].position if read_first else 0
    read_after = mine(await store.across(FEEDS, after=cursor), early, late)
    whole = mine(await store.across(FEEDS), early, late)
    assert [row.entry.call for row in whole] == [early, late]
    assert [row.position for row in [*read_first, *read_after]] == [row.position for row in whole]


async def test_an_agents_newest_calls_come_newest_first(
    store: Store, call: str, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The operator's newest calls of an agent, newest first, and no other agent's."""
    older, newer = f"{call}-a", f"{call}-b"
    await store.append(older, agent, "call.ringing", {}, ephemeral=False)
    await store.append(newer, f"{agent}-2", "call.ringing", {}, ephemeral=False)
    async with sessions() as session:
        assert await lists.newest_calls(session, 5, agent=agent) == [older]
        assert await lists.newest_calls(session, 5, agent=f"{agent}-2") == [newer]


# ── the table itself ──

A_ROW = text(
    "insert into call_log (call, seq, ts, agent, type, ephemeral, data)"
    " values (:call, :seq, 1.0, :agent, :type, false, '{}')"
)


async def test_the_table_refuses_an_update_and_a_delete(
    engine: AsyncEngine, store: Store, call: str, agent: str
) -> None:
    """call_log is append-only: Postgres itself refuses to change or remove a row."""
    await store.append(call, agent, "call.started", {}, ephemeral=False)
    for statement in (
        "update call_log set type = 'nope' where call = :call",
        "delete from call_log where call = :call",
    ):
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError, match="append-only"):
                await connection.execute(text(statement), {"call": call})
    assert [entry.type for entry in await store.since(call)] == ["call.started"]


async def test_the_table_refuses_an_entry_on_a_sealed_log_but_its_verdict(
    engine: AsyncEngine, store: Store, call: str, agent: str
) -> None:
    """A sealed log takes no entry, at the table, but the verdict that may land after the seal."""
    await store.append(call, agent, "call.started", {}, ephemeral=False)
    await store.seal(call)
    row = {"call": call, "agent": agent}
    async with engine.connect() as connection:
        with pytest.raises(DBAPIError, match="sealed"):
            await connection.execute(A_ROW, {**row, "seq": 2, "type": "turn.user"})
    async with engine.begin() as connection:
        await connection.execute(A_ROW, {**row, "seq": 2, "type": "call.score"})
    assert [entry.type for entry in await store.since(call)] == ["call.started", "call.score"]


async def test_a_sealed_head_is_never_opened_again(engine: AsyncEngine, store: Store, call: str, agent: str) -> None:
    """Unsealing a head is refused by the table, and a later claim moves nothing."""
    await store.append(call, agent, "call.started", {}, ephemeral=False)
    await store.claim(call, agent, "clinica")
    await store.seal(call)
    async with engine.connect() as connection:
        with pytest.raises(DBAPIError, match="sealed"):
            await connection.execute(text("update call_log_head set sealed = false where log = :log"), {"log": call})
    await store.claim(call, agent, "tienda")
    assert await store.is_sealed(call)
    assert await store.claimant(call, agent) == Claimant("clinica", None)


async def test_the_golden_log_replays_to_the_same_state_through_postgres(
    sessions: async_sessionmaker[AsyncSession], call: str
) -> None:
    """The SDKs' golden log, appended entry by entry, reads back and folds to the golden state."""
    ticks = iter(entry.ts for entry in GOLDEN)
    store = Store(sessions, clock=lambda: next(ticks))
    for entry in GOLDEN:
        await store.append(call, entry.agent, entry.type, entry.data, ephemeral=entry.ephemeral)
    await store.writer.drain()
    written = await store.whole(call)
    # The golden is a reader's stream, with a gap in it, so it is compared renumbered.
    durable = [
        entry.model_copy(update={"seq": seq, "call": call})
        for seq, entry in enumerate(GOLDEN, 1)
        if not entry.ephemeral
    ]
    assert await store.latest_seq(call) == len(GOLDEN)
    assert [entry.dump() for entry in written] == [entry.dump() for entry in durable]
    state = reduce(written).dump()
    assert state == reduce(durable).dump()
    for field in ("app_state", "turns", "usage", "cost"):
        assert state[field] == EXPECTED[field]


WRITER = textwrap.dedent(
    """
    import asyncio, sys
    from pinecall_runtime.calls.store import Store
    from pinecall_runtime.config import load_settings
    from pinecall_runtime.postgres import create_engine, session_maker

    async def main(call, agent):
        store = Store(session_maker(create_engine(load_settings(), pool_size=1)))
        while True:
            entry = await store.append(call, agent, "custom", {"name": "tick", "data": {}}, ephemeral=False)
            sys.stdout.write(f"{entry.seq}\\n")
            sys.stdout.flush()

    asyncio.run(main(*sys.argv[1:3]))
    """
)
APPENDS_BEFORE_THE_KILL = 30


# One statement writes the counter and the row, so a writer killed between them cannot exist.
@pytest.mark.timeout(60)
async def test_a_killed_writer_leaves_a_contiguous_log_and_no_torn_row(store: Store, call: str, agent: str) -> None:
    """SIGKILL in the middle of appends leaves no hole, no torn row, and a counter that matches."""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", WRITER, call, agent, stdout=asyncio.subprocess.PIPE, env=dict(os.environ)
    )
    assert process.stdout is not None
    try:
        last = 0
        for _ in range(APPENDS_BEFORE_THE_KILL):
            last = int(await asyncio.wait_for(process.stdout.readline(), timeout=20))
        # SIGKILL, not terminate: the writer must not get to finish its append.
        process.send_signal(signal.SIGKILL)
        assert await process.wait() == -signal.SIGKILL
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    entries = await store.whole(call)
    assert [entry.seq for entry in entries] == list(range(1, len(entries) + 1)), "a hole"
    assert len(entries) >= last, "an entry the writer was told it had is not there"
    assert await store.latest_seq(call) == len(entries), "an unfinished append moved the counter"
    assert all(entry.data == {"name": "tick", "data": {}} for entry in entries), "a torn row"


# Two gateways are two stores on one database: the lease is the holder's to renew or give back.
async def test_a_seals_lease_is_renewed_and_given_back_by_its_holder_alone(
    sessions: async_sessionmaker[AsyncSession], store: Store, call: str
) -> None:
    """Another gateway can neither renew nor release this one's lease, and takes it once it lapses."""
    other = Store(sessions, clock=store.clock)
    assert await store.lease_seal(call, 1.0)
    await other.renew_seal(call, 60.0)
    await other.release_seal(call)
    assert not await other.lease_seal(call, 60.0), "neither renewed nor released by the other"
    await asyncio.sleep(1.1)
    assert await other.lease_seal(call, 60.0), "lapsed, the other takes it"
    await store.renew_seal(call, 60.0)
    await store.release_seal(call)
    assert not await store.lease_seal(call, 60.0), "the one that lost it cannot touch it"
    await other.writer.drain()
