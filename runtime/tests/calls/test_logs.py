"""The org's feed: what it says of a tool that ran and nothing of what it did; and a reader's markers."""

import asyncio
from collections.abc import AsyncGenerator
from typing import cast, override

from pinecall_runtime.agents.declaration import Versions
from pinecall_runtime.calls.fanout import Subscription
from pinecall_runtime.calls.logs import Logs
from pinecall_runtime.calls.repository.heads import Claim
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.redis import Listener, LocalSignal
from pinecall_runtime.wire.base import Entry
from tests.conftest import needs_the_database, until

pytestmark = needs_the_database

ORG = "clinica"
HEARD_WITHIN_S = 2.0


async def heard(feed: Subscription) -> Entry:
    """The next entry of the feed, or a failure when none comes."""
    return await asyncio.wait_for(anext(feed), HEARD_WITHIN_S)


async def test_a_tool_that_answered_or_failed_is_said_on_the_feed_with_its_name_and_seconds_alone(
    store: Store, call: str, agent: str
) -> None:
    """The arguments, the output and the error stay in the call's log: the feed names the tool and the call."""
    logs = Logs(store)
    await store.claim(call, agent, ORG, Claim(Scope(ORG, Env.sandbox), Versions(config=1)))
    feed = await logs.feed_reader(ORG, Env.sandbox)
    log = logs.writing(call, agent)
    asked = {"arguments": {"dni": "12345678Z"}, "speech_id": "s1"}
    await log.append("tool.call", {"call_id": "tc_1", "name": "find_slots", **asked})
    await log.answer({"call_id": "tc_1", "name": "find_slots", "output": {"patient": "Marta"}, "duration_s": 0.2})
    await log.append("tool.call", {"call_id": "tc_2", "name": "book_slot", **asked})
    await log.answer({"call_id": "tc_2", "name": "book_slot", "error": "no agenda for Marta Ruiz"})
    ran, failed = await heard(feed), await heard(feed)
    assert (ran.type, ran.ephemeral, ran.call, ran.seq) == ("tool.ran", True, None, 0)
    assert ran.data == {"call": call, "agent": agent, "name": "find_slots", "duration_s": 0.2}
    assert failed.type == "tool.failed"
    assert failed.data == {"call": call, "agent": agent, "name": "book_slot", "duration_s": None}
    for said in (ran, failed):
        assert "Marta" not in str(said.data) and "12345678Z" not in str(said.data)
    feed.close()


async def test_a_tool_of_another_env_is_not_said_on_this_envs_feed(store: Store, call: str, agent: str) -> None:
    """The feed is the org's in one env: the sandbox's tools never reach a production reader."""
    logs = Logs(store)
    await store.claim(call, agent, ORG, Claim(Scope(ORG, Env.sandbox), Versions(config=1)))
    production = await logs.feed_reader(ORG, Env.production)
    sandbox = await logs.feed_reader(ORG, Env.sandbox)
    log = logs.writing(call, agent)
    await log.append("tool.call", {"call_id": "tc_1", "name": "find_slots", "arguments": {}, "speech_id": "s1"})
    await log.answer({"call_id": "tc_1", "name": "find_slots"})
    assert (await heard(sandbox)).type == "tool.ran"
    await asyncio.sleep(0.05)
    production.close()
    assert [entry async for entry in production] == []
    sandbox.close()


async def test_a_reader_resumed_at_the_end_is_told_it_caught_up_by_the_agent_whose_log_it_is(
    store: Store, call: str, agent: str
) -> None:
    """A reader's log is made before anybody says whose it is: its marker names the agent the entries do."""
    await store.claim(call, agent, ORG, Claim(Scope(ORG, Env.sandbox), Versions(config=1)))
    written = await Logs(store).writing(call, agent).append("custom", {"name": "x", "data": {}})
    reading = Logs(store).reading(call).stream(after=written.seq)
    caught_up = await asyncio.wait_for(anext(reading), HEARD_WITHIN_S)
    assert (caught_up.type, caught_up.agent) == ("log.caught_up", agent)
    await cast(AsyncGenerator[Entry], reading).aclose()


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
    logs = Logs(store, signal)
    await store.claim(call, agent, ORG, Claim(Scope(ORG, Env.sandbox), Versions(config=1)))
    following = asyncio.create_task(logs.reading(call).follow())
    await asyncio.wait_for(signal.asked.wait(), HEARD_WITHIN_S)
    logs.reading(f"{call}_another")
    signal.confirm.set()
    reader = await asyncio.wait_for(following, HEARD_WITHIN_S)
    written = await logs.writing(call, agent).append("custom", {"name": "x", "data": {}})
    assert (await heard(reader)).seq == written.seq
    reader.close()
    await logs.close()


async def test_a_follow_that_fails_lets_its_reader_go(store: Store, call: str) -> None:
    signal = SlowSignal()
    logs = Logs(store, signal)
    log = logs.reading(call)
    following = asyncio.create_task(log.follow())
    await asyncio.wait_for(signal.asked.wait(), HEARD_WITHIN_S)
    assert log.fanout.readers == 1
    following.cancel()
    await asyncio.gather(following, return_exceptions=True)
    await until(lambda: log.fanout.readers == 0)
    await logs.close()
