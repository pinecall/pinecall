"""Entries of one made-up call, built the way a gateway writes them, for the reducer's tests."""

from pinecall.wire._names import Json, JsonObject
from pinecall.wire.frames import Entry

CALL = "CA_7d1e"
AGENT = "dental-sur"
LINE: JsonObject = {"channel": "phone", "from": "+34611222333", "to": "+34955111222"}
CALLER: JsonObject = {"id": "ct_9", "phone": "+34611222333", "name": "Marta"}
ROOM: JsonObject = {"name": "call-CA_7d1e", "sid": "RM_9", "channel": "phone"}
SEAT: JsonObject = {"identity": "sip_caller", "kind": "caller", "attributes": {"sip.trunk": "t"}}
TOOL: JsonObject = {"call_id": "tc_1", "name": "free_slots", "arguments": {"on": "friday"}}
BOSS: JsonObject = {"id": "sup_4", "name": "Irene"}


def entry(seq: int, kind: str, data: JsonObject, *, ephemeral: bool = False) -> Entry:
    return Entry(
        seq=seq,
        ts=1_790_000_000.0 + seq,
        call=CALL,
        agent=AGENT,
        type=kind,
        ephemeral=ephemeral,
        data=data,
    )


def a_summary(usage: list[Json]) -> JsonObject:
    return {
        "reason": "caller_hung_up",
        "outcome": "moved the appointment",
        "duration_s": 120.0,
        "turns": 8,
        "usage": usage,
        "cost": {
            "usd": 0.02,
            "rows": [],
            "unpriced": [],
        },
    }
