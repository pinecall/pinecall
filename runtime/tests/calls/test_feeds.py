"""The feeds' word on a call: the lifecycle with no content, a tool's name and seconds, nothing of what it did."""

import time

from pinecall_runtime.calls import feeds
from pinecall_runtime.calls.relay import BOX_CHANNEL
from pinecall_runtime.calls.repository.heads import Claimant
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.base import Entry


def an_entry(kind: str, data: JsonObject, call: str | None = "call_1") -> Entry:
    return Entry(seq=1, ts=time.time(), call=call, agent="clinica-norte", type=kind, ephemeral=False, data=data)


def test_the_feeds_carry_the_lifecycle_and_leave_a_calls_content_out() -> None:
    assert feeds.on_the_feeds(an_entry("turn.agent", {"text": "hola"})) is None
    started = an_entry("call.started", {"from": "+34600000000"})
    assert feeds.on_the_feeds(started) is started
    scored = feeds.on_the_feeds(an_entry("call.score", {"judges": [{"name": "promises", "verdict": "broken"}]}))
    assert scored is not None and scored.data == {}


def test_an_agents_own_entry_reaches_the_orgs_feed_in_both_envs_and_a_calls_in_its_own() -> None:
    both = (BOX_CHANNEL, "feed:clinica:production", "feed:clinica:sandbox")
    assert feeds.feed_channels(Claimant("clinica", None)) == both
    assert feeds.feed_channels(Claimant("clinica", Env.sandbox)) == (BOX_CHANNEL, "feed:clinica:sandbox")


def test_a_tool_is_said_with_its_name_and_seconds_alone() -> None:
    answered = {"call_id": "tc_1", "name": "find_slots", "output": {"patient": "Marta"}, "duration_s": 0.2}
    ran = feeds.tool_news(an_entry("tool.result", answered), Claimant("clinica", Env.sandbox))
    assert ran is not None
    scope, kind, event = ran
    assert (scope.org, scope.env, kind) == ("clinica", Env.sandbox, "tool.ran")
    assert event.dump() == {"call": "call_1", "agent": "clinica-norte", "name": "find_slots", "duration_s": 0.2}
    broke = {"call_id": "tc_2", "name": "book", "error": "no agenda"}
    failed = feeds.tool_news(an_entry("tool.result", broke), Claimant("clinica", Env.sandbox))
    assert failed is not None and failed[1] == "tool.failed" and "no agenda" not in str(failed[2].dump())


def test_a_tool_of_an_agents_own_log_or_of_a_claimant_with_no_env_is_not_said() -> None:
    result: JsonObject = {"call_id": "tc_1", "name": "find_slots"}
    assert feeds.tool_news(an_entry("tool.result", result, call=None), Claimant("clinica", Env.sandbox)) is None
    assert feeds.tool_news(an_entry("tool.result", result), Claimant("clinica", None)) is None
    assert feeds.tool_news(an_entry("tool.result", {"nonsense": True}), Claimant("clinica", Env.sandbox)) is None
