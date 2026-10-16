"""A call's facts: the row its log folds to, entry by entry, for the lists and the series to read."""

from dataclasses import replace

from pinecall_runtime.calls.facts import LINE_FIELDS, CallFacts, fold, line_of
from pinecall_runtime.calls.reducer import reduce
from pinecall_runtime.kit.text import Json, JsonObject
from pinecall_runtime.wire.base import Entry
from tests.calls.factories import AGENT, EXPECTED, GOLDEN


def logged(kind: str, data: JsonObject, *, ephemeral: bool = False) -> Entry:
    """One entry of call CA_x."""
    return Entry(seq=1, ts=5.0, call="CA_x", agent=AGENT, type=kind, ephemeral=ephemeral, data=data)


def judgment(name: str, verdict: str, reason: str = "") -> JsonObject:
    """One judge's verdict, as a call.score carries it."""
    return {"name": name, "verdict": verdict, "criteria": "c", "reason": reason, "evidence": {"seqs": []}}


def test_an_entry_of_no_call_or_an_ephemeral_one_changes_no_fact() -> None:
    facts = CallFacts(call="CA_x")
    assert (
        fold(
            facts,
            logged("turn.user", {"speech_id": "u", "text": "x", "metrics": {}}, ephemeral=True),
        )
        == facts
    )
    own = logged("agent.registered", {"routes": [], "app": "a"}).model_copy(update={"call": None})
    assert fold(facts, own) == facts


def test_an_entry_nobody_can_read_changes_no_fact_and_raises_nothing() -> None:
    facts = CallFacts(call="CA_x", outcome="kept")
    assert fold(facts, logged("call.summary", {"duration_s": "long"})) == facts
    assert fold(facts, logged("nobody.knows", {})) == facts


def test_a_person_taking_part_escalates_the_call_whatever_the_shape() -> None:
    assert fold(CallFacts(call="CA_x"), logged("supervisor.said", {"anything": 1})).escalated
    assert not fold(CallFacts(call="CA_x"), logged("supervisor.whispered", {"anything": 1})).escalated


def test_the_reason_the_call_ended_with_is_kept_over_the_summarys() -> None:
    ended: JsonObject = {
        "reason": "transferred",
        "ended_by": "agent",
        "ended_at": 9.0,
        "duration_s": 8.0,
    }
    facts = fold(CallFacts(call="CA_x"), logged("call.ended", ended))
    assert (facts.end_reason, facts.escalated, facts.ended_at) == ("transferred", True, 9.0)
    summary: JsonObject = {
        "reason": "caller_hung_up",
        "outcome": "o",
        "duration_s": 8.0,
        "turns": 1,
        "usage": [],
        "cost": {
            "usd": 0.1,
            "rows": [],
            "unpriced": [],
        },
    }
    assert fold(facts, logged("call.summary", summary)).end_reason == "transferred"


def test_a_summarys_rows_fold_to_the_calls_cost_by_stage_and_the_boxs_own_apart() -> None:
    def row(provider: str, unit: str, usd: float) -> JsonObject:
        return {
            "provider": provider,
            "model": "m",
            "unit": unit,
            "quantity": 1,
            "unit_price_usd": usd,
            "usd": usd,
        }

    rows: list[Json] = [
        row("anthropic", "input_tokens", 0.1),
        row("anthropic", "output_tokens", 0.2),
        row("cartesia", "characters", 0.4),
        row("deepgram", "audio_seconds", 0.8),
        row("twilio", "minutes", 1.6),
        row("pinecall", "minutes", 3.2),
    ]
    summary: JsonObject = {
        "reason": "caller_hung_up",
        "outcome": "o",
        "duration_s": 8.0,
        "turns": 1,
        "usage": [],
        "cost": {"usd": 6.3, "rows": rows, "unpriced": []},
    }
    facts = fold(CallFacts(call="CA_x"), logged("call.summary", summary))
    by_stage = (
        facts.cost_llm_usd,
        facts.cost_stt_usd,
        facts.cost_tts_usd,
        facts.cost_phone_usd,
        facts.cost_platform_usd,
    )
    assert (facts.cost_usd, by_stage) == (6.3, (0.3, 0.8, 0.4, 1.6, 3.2))


def test_a_verdict_nobody_settled_is_no_score() -> None:
    skipped = fold(
        CallFacts(call="CA_x"),
        logged("call.score", {"judges": [judgment("consent", "skipped")], "judge_calls": 1}),
    )
    assert (skipped.judged, skipped.held, skipped.passed, skipped.score, skipped.flags) == (
        0,
        0,
        None,
        None,
        [],
    )


def test_a_web_call_is_spoken_once_a_room_opens_and_a_phone_call_always() -> None:
    web = fold(
        CallFacts(call="CA_x"),
        logged(
            "call.started",
            {
                "channel": "web",
                "direction": "inbound",
                "from": "v",
                "to": "a",
                "caller": None,
                "started_at": 1.0,
            },
        ),
    )
    assert not web.spoken
    assert fold(web, logged("room.opened", {"name": "r", "sid": "s", "channel": "web"})).spoken
    phone = fold(
        CallFacts(call="CA_x"),
        logged(
            "call.ringing",
            {
                "channel": "phone",
                "from": "+1",
                "to": "+2",
                "route": {"channel": "phone", "number": "+2"},
                "caller": {"id": "ct_9", "name": "Ana"},
            },
        ),
    )
    assert (phone.spoken, phone.contact, phone.name, phone.direction) == (
        True,
        "ct_9",
        "Ana",
        "inbound",
    )


def test_the_line_a_list_shows_is_the_states_own_fields_and_a_fold_leaves_it() -> None:
    """The golden log's line is the golden state's fields, cursor included; folding entries keeps it."""
    line = line_of(reduce(GOLDEN))
    assert set(line) == set(LINE_FIELDS)
    assert {name: EXPECTED.get(name) for name in LINE_FIELDS} == line
    assert line["seq"] == EXPECTED["seq"]
    kept = replace(CallFacts(call="CA_x"), line=line)
    assert fold(kept, logged("call.ended", {"reason": "caller_hung_up", "duration_s": 2.0})).line == line
