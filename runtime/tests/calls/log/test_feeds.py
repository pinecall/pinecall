"""The feeds' word on a call: the lifecycle with no content, a tool's name and seconds, nothing of what it did."""

import asyncio
import time

from runtime.actor import Scope
from runtime.agents.settings import Versions
from runtime.calls.log import feeds
from runtime.calls.log.fanout import Subscription
from runtime.calls.log.relay import BOX_CHANNEL
from runtime.calls.log.store import Store
from runtime.calls.repository.heads import Claim, Claimant
from runtime.enums import Env
from runtime.kit.text import JsonObject
from runtime.wire.base import Entry
from tests.calls.factories import claim_call, logs_on
from tests.conftest import needs_the_database


def an_entry(kind: str, data: JsonObject, call: str | None = "call_1") -> Entry:
    return Entry(seq=1, ts=time.time(), call=call, agent="clinica-norte", type=kind, ephemeral=False, data=data)


def test_the_feeds_carry_the_lifecycle_and_leave_a_calls_content_out() -> None:
    assert feeds.feed_entry_of(an_entry("turn.agent", {"text": "hola"})) is None
    started = an_entry("call.started", {"from": "+34600000000"})
    assert feeds.feed_entry_of(started) is started
    scored = feeds.feed_entry_of(an_entry("call.score", {"judges": [{"name": "promises", "verdict": "broken"}]}))
    assert scored is not None and scored.data == {}


def test_an_agents_own_entry_reaches_the_orgs_feed_in_both_envs_and_a_calls_in_its_own() -> None:
    both = (BOX_CHANNEL, "feed:clinica:production", "feed:clinica:sandbox")
    assert feeds.feed_channels(Claimant("clinica", None)) == both
    assert feeds.feed_channels(Claimant("clinica", Env.sandbox)) == (BOX_CHANNEL, "feed:clinica:sandbox")


def test_a_tool_is_said_with_its_name_and_seconds_alone() -> None:
    answered = {"call_id": "tc_1", "name": "find_slots", "output": {"patient": "Marta"}, "duration_s": 0.2}
    ran = feeds.tool_news(an_entry("tool.result", answered), Claimant("clinica", Env.sandbox))
    assert ran is not None
    assert (ran.scope.org, ran.scope.env, ran.kind) == ("clinica", Env.sandbox, "tool.ran")
    assert ran.event.dump() == {"call": "call_1", "agent": "clinica-norte", "name": "find_slots", "duration_s": 0.2}
    broke = {"call_id": "tc_2", "name": "book", "error": "no agenda"}
    failed = feeds.tool_news(an_entry("tool.result", broke), Claimant("clinica", Env.sandbox))
    assert failed is not None and failed.kind == "tool.failed" and "no agenda" not in str(failed.event.dump())


def test_a_tool_of_an_agents_own_log_or_of_a_claimant_with_no_env_is_not_said() -> None:
    result: JsonObject = {"call_id": "tc_1", "name": "find_slots"}
    assert feeds.tool_news(an_entry("tool.result", result, call=None), Claimant("clinica", Env.sandbox)) is None
    assert feeds.tool_news(an_entry("tool.result", result), Claimant("clinica", None)) is None
    assert feeds.tool_news(an_entry("tool.result", {"nonsense": True}), Claimant("clinica", Env.sandbox)) is None


ORG = "clinica"
HEARD_WITHIN_S = 2.0


async def heard(feed: Subscription) -> Entry:
    """The next entry of the feed, or a failure when none comes."""
    return await asyncio.wait_for(anext(feed), HEARD_WITHIN_S)


@needs_the_database
async def test_a_tool_that_answered_or_failed_is_said_on_the_feed_with_its_name_and_seconds_alone(
    store: Store, call: str, agent: str
) -> None:
    """The arguments, the output and the error stay in the call's log: the feed names the tool and the call."""
    parts = logs_on(store)
    logs = parts.logs
    await claim_call(store, call, agent, Claim(Scope(ORG, Env.sandbox), Versions(settings=1)))
    feed = await parts.feeds.reader_of(ORG, Env.sandbox)
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


@needs_the_database
async def test_a_tool_of_another_env_is_not_said_on_this_envs_feed(store: Store, call: str, agent: str) -> None:
    """The feed is the org's in one env: the sandbox's tools never reach a production reader."""
    parts = logs_on(store)
    logs = parts.logs
    await claim_call(store, call, agent, Claim(Scope(ORG, Env.sandbox), Versions(settings=1)))
    production = await parts.feeds.reader_of(ORG, Env.production)
    sandbox = await parts.feeds.reader_of(ORG, Env.sandbox)
    log = logs.writing(call, agent)
    await log.append("tool.call", {"call_id": "tc_1", "name": "find_slots", "arguments": {}, "speech_id": "s1"})
    await log.answer({"call_id": "tc_1", "name": "find_slots"})
    assert (await heard(sandbox)).type == "tool.ran"
    await asyncio.sleep(0.05)
    production.close()
    assert [entry async for entry in production] == []
    sandbox.close()
