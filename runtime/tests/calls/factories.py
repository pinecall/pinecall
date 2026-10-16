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
