"""A log's readers: the marker a resumed one is told, and the reader a prune or a failed follow must not lose."""

import asyncio
from typing import override

from runtime.actor import Scope
from runtime.agents.settings import Versions
from runtime.calls.log.fanout import Subscription
from runtime.calls.log.store import Store
from runtime.calls.repository.heads import Claim
from runtime.enums import Env
from runtime.signal import Listener, LocalSignal
from runtime.wire.base import Entry
from tests.calls.factories import claim_call, logs_on
from tests.conftest import needs_the_database, until

pytestmark = needs_the_database

ORG = "clinica"
HEARD_WITHIN_S = 2.0


async def heard(feed: Subscription) -> Entry:
    """The next entry of the feed, or a failure when none comes."""
    return await asyncio.wait_for(anext(feed), HEARD_WITHIN_S)


async def test_a_reader_resumed_at_the_end_is_told_it_caught_up_by_the_agent_whose_log_it_is(
    store: Store, call: str, agent: str
) -> None:
    """A reader's log is made before anybody says whose it is: its marker names the agent the entries do."""
    await claim_call(store, call, agent, Claim(Scope(ORG, Env.sandbox), Versions(settings=1)))
    written = await logs_on(store).logs.writing(call, agent).append("custom", {"name": "x", "data": {}})
    reading = logs_on(store).logs.reading(call).stream(after=written.seq)
    caught_up = await asyncio.wait_for(anext(reading), HEARD_WITHIN_S)
    assert (caught_up.type, caught_up.agent) == ("log.caught_up", agent)
    await reading.aclose()


class SlowSignal(LocalSignal):
    """A signal whose subscription is confirmed only when the test says, as Redis's is after a round trip."""

    def __init__(self) -> None:
        super().__init__()
        self.asked = asyncio.Event()
        self.confirm = asyncio.Event()

    @override
    async def subscribe(self, channel: str) -> Listener:
        self.asked.set()
        await self.confirm.wait()
        return await super().subscribe(channel)


# G B4 (2026-10-23): `simulate --voice` printed nothing until the call was over. Its reader's log was made with
# no reader yet, and another request's prune dropped it while the follow waited for the signal: the reader
# was left on a copy the relay never delivers to, and heard nothing live, its call's end included.
async def test_a_reader_still_waiting_for_its_follow_is_not_pruned_and_hears_what_is_written(
    store: Store, call: str, agent: str
) -> None:
    signal = SlowSignal()
    parts = logs_on(store, signal)
    logs = parts.logs
    await claim_call(store, call, agent, Claim(Scope(ORG, Env.sandbox), Versions(settings=1)))
    following = asyncio.create_task(logs.reading(call).follow())
    await asyncio.wait_for(signal.asked.wait(), HEARD_WITHIN_S)
    logs.reading(f"{call}_another")
    signal.confirm.set()
    reader = await asyncio.wait_for(following, HEARD_WITHIN_S)
    written = await logs.writing(call, agent).append("custom", {"name": "x", "data": {}})
    assert (await heard(reader)).seq == written.seq
    reader.close()
    await parts.relay.close()


# 2026-11-06: of nine streams a comparison opened at once, three never heard their call end. Each request
# made its log before its stream started, and the next request's prune dropped the ones not yet subscribed.
async def test_a_stream_another_request_prunes_around_before_it_starts_hears_its_call_live(
    store: Store, call: str, agent: str
) -> None:
    parts = logs_on(store)
    logs = parts.logs
    await claim_call(store, call, agent, Claim(Scope(ORG, Env.sandbox), Versions(settings=1)))
    reading = logs.stream(call)
    logs.reading(f"{call}_another")
    assert (await asyncio.wait_for(anext(reading), HEARD_WITHIN_S)).type == "log.caught_up"
    written = await logs.writing(call, agent).append("custom", {"name": "x", "data": {}})
    assert (await asyncio.wait_for(anext(reading), HEARD_WITHIN_S)).seq == written.seq
    await reading.aclose()


async def test_a_stream_that_fell_behind_keeps_its_log_while_it_follows_again(
    store: Store, call: str, agent: str
) -> None:
    parts = logs_on(store)
    logs = parts.logs
    await claim_call(store, call, agent, Claim(Scope(ORG, Env.sandbox), Versions(settings=1)))
    reading = logs.stream(call)
    assert (await asyncio.wait_for(anext(reading), HEARD_WITHIN_S)).type == "log.caught_up"
    logs.reading(call).fanout.drop()
    assert (await asyncio.wait_for(anext(reading), HEARD_WITHIN_S)).type == "log.gap"
    logs.reading(f"{call}_another")
    assert (await asyncio.wait_for(anext(reading), HEARD_WITHIN_S)).type == "log.caught_up"
    written = await logs.writing(call, agent).append("custom", {"name": "x", "data": {}})
    assert (await asyncio.wait_for(anext(reading), HEARD_WITHIN_S)).seq == written.seq
    await reading.aclose()


async def test_a_follow_that_fails_lets_its_reader_go(store: Store, call: str) -> None:
    signal = SlowSignal()
    parts = logs_on(store, signal)
    logs = parts.logs
    log = logs.reading(call)
    following = asyncio.create_task(log.follow())
    await asyncio.wait_for(signal.asked.wait(), HEARD_WITHIN_S)
    assert log.fanout.readers == 1
    following.cancel()
    await asyncio.gather(following, return_exceptions=True)
    await until(lambda: log.fanout.readers == 0)
    await parts.relay.close()
