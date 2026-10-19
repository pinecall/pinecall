"""A call's entries as the calls engine's tests write them: one line each, the golden log beside them."""

import json
from pathlib import Path

from pydantic import TypeAdapter

from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.wire.base import Entry

THE_GOLDEN = Path(__file__).resolve().parents[1] / "wire" / "golden"
GOLDEN: list[Entry] = TypeAdapter(list[Entry]).validate_json((THE_GOLDEN / "call-log.json").read_bytes())
EXPECTED: JsonObject = json.loads((THE_GOLDEN / "call-log.state.json").read_text(encoding="utf-8"))

CALL = "CA_7d1e"
AGENT = "dental-sur"
LINE: JsonObject = {"channel": "phone", "from": "+34611222333", "to": "+34955111222"}
CALLER: JsonObject = {"id": "ct_9", "phone": "+34611222333", "name": "Marta"}
ROOM: JsonObject = {"name": "call-CA_7d1e", "sid": "RM_9", "channel": "phone"}
SEAT: JsonObject = {"identity": "sip_caller", "kind": "caller", "attributes": {"sip.trunk": "t"}}
TOOL: JsonObject = {"call_id": "tc_1", "name": "free_slots", "arguments": {"on": "friday"}}
BOSS: JsonObject = {"id": "sup_4", "name": "Irene"}


def entry(seq: int, kind: str, data: JsonObject, *, ephemeral: bool = False) -> Entry:
    """One entry of the call, a second after the one before it."""
    return Entry(seq=seq, ts=1_790_000_000.0 + seq, call=CALL, agent=AGENT, type=kind, ephemeral=ephemeral, data=data)


def a_summary(usage: list[Json]) -> JsonObject:
    """A call.summary's data: two minutes, eight turns, two cents, and the usage given."""
    return {
        "reason": "caller_hung_up",
        "outcome": "moved the appointment",
        "duration_s": 120.0,
        "turns": 8,
        "usage": usage,
        "cost": {"usd": 0.02, "rows": [], "unpriced": []},
    }


def a_user_turn(speech: str, **metrics: float) -> JsonObject:
    """A turn.user's data: this speech id and these metrics."""
    return {"speech_id": speech, "text": "hola", "metrics": dict(metrics)}


def an_agent_turn(speech: str, **metrics: float) -> JsonObject:
    """A turn.agent's data: this speech id and these metrics."""
    return {"speech_id": speech, "text": "buenas", "interrupted": False, "metrics": dict(metrics)}


def a_tool_call(call_id: str, name: str, speech: str) -> JsonObject:
    """A tool.call's data, asked in this speech."""
    return {"call_id": call_id, "name": name, "arguments": {}, "speech_id": speech}


def a_tool_result(call_id: str, name: str, *, error: str | None = None, seconds: float | None = None) -> JsonObject:
    """A tool.result's data: its error when it failed, its seconds when it was timed."""
    result: JsonObject = {"call_id": call_id, "name": name, "output": {"slots": ["09:30"]}}
    if error is not None:
        result = {"call_id": call_id, "name": name, "error": error}
    if seconds is not None:
        result["duration_s"] = seconds
    return result


# Marta's call: two tools in the first turn (the second fails), four replies of which the three slowest
# are kept (seq 9, 0.8 s, is not), and a last tool that timed out with no seconds.
def a_call_with_tools(call: str = CALL, agent: str = AGENT) -> list[Entry]:
    """The entries of that call, from its start to the last tool's timeout."""

    def at(seq: int, kind: str, data: JsonObject) -> Entry:
        return entry(seq, kind, data).model_copy(update={"call": call, "agent": agent})

    started: JsonObject = {**LINE, "direction": "inbound", "caller": CALLER, "started_at": 1_790_000_000.0}
    return [
        at(1, "call.started", started),
        at(2, "turn.user", a_user_turn("s1", transcription_delay=0.2)),
        at(3, "tool.call", a_tool_call("tc_1", "find_slots", "s1")),
        at(4, "tool.result", a_tool_result("tc_1", "find_slots", seconds=0.4)),
        at(5, "tool.call", a_tool_call("tc_2", "book_slot", "s1")),
        at(6, "tool.result", a_tool_result("tc_2", "book_slot", error="slot taken", seconds=0.2)),
        at(7, "turn.agent", an_agent_turn("s1", e2e_latency=2.0, llm_node_ttft=0.5, tts_node_ttfb=0.3)),
        at(8, "turn.user", a_user_turn("s2", transcription_delay=0.1)),
        at(9, "turn.agent", an_agent_turn("s2", e2e_latency=0.8, llm_node_ttft=0.3, tts_node_ttfb=0.2)),
        at(10, "turn.agent", an_agent_turn("s3", e2e_latency=1.5)),
        at(11, "turn.user", a_user_turn("s4", transcription_delay=0.3)),
        at(12, "turn.agent", an_agent_turn("s4", e2e_latency=1.2, llm_node_ttft=0.4)),
        at(13, "tool.call", a_tool_call("tc_3", "book_slot", "s5")),
        at(14, "tool.result", a_tool_result("tc_3", "book_slot", error="book_slot did not answer within 10s")),
    ]
