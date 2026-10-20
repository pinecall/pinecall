"""What a log meters: each summary, score and try a usage row, and the totals per org."""

from pinecall_runtime.calls.metering import UNOWNED, lent_row, totals_by_org, usage_row
from pinecall_runtime.calls.repository.entries import Positioned
from pinecall_runtime.calls.writer import METERED_TYPES
from pinecall_runtime.kit.text import JsonObject
from tests.calls.factories import CALL, a_summary, entry

LLM: JsonObject = {
    "type": "llm_usage",
    "provider": "anthropic",
    "model": "haiku",
    "input_tokens": 900,
    "output_tokens": 150,
}
TTS: JsonObject = {
    "type": "tts_usage",
    "provider": "cartesia",
    "model": "sonic",
    "characters_count": 320,
}
STT: JsonObject = {
    "type": "stt_usage",
    "provider": "deepgram",
    "model": "nova",
    "audio_duration": 118.0,
}
A_SCORE: JsonObject = {
    "passed": True,
    "judges": [],
    "judge_calls": 3,
    "evals": 2,
    "judge_cost_usd": 0.004,
}


def metered(position: int, org: str | None, kind: str, data: JsonObject, call: str = CALL) -> Positioned:
    return Positioned(
        position=position,
        org=org,
        entry=entry(position, kind, data).model_copy(update={"call": call}),
    )


def test_a_summary_counts_minutes_turns_the_llms_tokens_and_the_tts_characters() -> None:
    row = usage_row(metered(7, "dental", "call.summary", a_summary([LLM, TTS, STT])))
    assert (row.cursor, row.org, row.call, row.type) == (7, "dental", CALL, "call.summary")
    used = row.used
    assert (used.calls, used.minutes, used.messages) == (1, 2.0, 8)
    assert (used.input_tokens, used.output_tokens, used.characters) == (900, 150, 320)
    assert (used.cost_usd, used.judge_calls, used.evals, used.simulations) == (0.02, 0, 0, 0)


def test_a_summary_a_simulated_caller_played_counts_one_simulation_and_no_minutes() -> None:
    simulated = {**a_summary([LLM]), "simulated": True}
    used = usage_row(metered(7, "dental", "call.summary", simulated)).used
    assert (used.simulations, used.calls, used.minutes) == (1, 1, 0.0)


def test_a_written_golden_of_an_eval_run_counts_no_minutes_and_no_simulation() -> None:
    run = {**a_summary([LLM]), "run": "run_8f4a2c"}
    used = usage_row(metered(7, "dental", "call.summary", run)).used
    assert (used.simulations, used.calls, used.minutes, used.messages) == (0, 1, 0.0, 8)


def test_a_judge_tried_counts_its_evals_and_none_on_the_orgs_own_key() -> None:
    tried: JsonObject = {
        "kind": "try",
        "name": "grounded",
        "env": "sandbox",
        "calls": ["CA_1", "CA_2"],
        "evals": 2,
        "judge_calls": 2,
        "judge_cost_usd": 0.002,
    }
    used = usage_row(metered(9, "dental", "evals.spent", tried)).used
    assert (used.evals, used.judge_calls, used.calls, used.minutes) == (2, 2, 0, 0.0)
    own = usage_row(metered(9, "dental", "evals.spent", {**tried, "own_key": True})).used
    assert own.evals == 0


def test_a_score_counts_its_judge_calls_its_evals_and_their_cost_and_nothing_else() -> None:
    used = usage_row(metered(8, "dental", "call.score", A_SCORE)).used
    assert (used.judge_calls, used.evals, used.cost_usd) == (3, 2, 0.004)
    assert (used.calls, used.minutes, used.simulations) == (0, 0.0, 0)


def test_a_score_judged_on_the_orgs_own_key_bills_no_eval_and_still_counts_its_calls() -> None:
    own = {**A_SCORE, "own_key": True}
    used = usage_row(metered(8, "dental", "call.score", own)).used
    assert (used.evals, used.judge_calls) == (0, 3)


def test_a_score_nobody_judged_costs_nothing_although_its_cost_is_null() -> None:
    nobody: JsonObject = {
        "passed": None,
        "not_judged": "no judge",
        "judges": [],
        "panel": None,
        "judge_calls": 0,
        "judge_cost_usd": None,
    }
    assert usage_row(metered(9, "dental", "call.score", nobody)).used.cost_usd == 0.0


def test_a_log_nobody_claimed_is_filed_as_unowned_rather_than_dropped() -> None:
    assert usage_row(metered(1, None, "call.summary", a_summary([]))).org == UNOWNED


def test_a_metered_entry_nobody_can_read_counts_nothing_and_does_not_stop_the_count() -> None:
    row = usage_row(metered(2, "dental", "call.summary", {"duration_s": "long"}))
    assert (row.cursor, row.used.calls, row.used.minutes) == (2, 0, 0.0)


def test_totals_add_up_per_org_and_count_a_call_once_for_its_summary() -> None:
    rows = [
        usage_row(metered(1, "dental", "call.summary", a_summary([LLM]), "CA_1")),
        usage_row(metered(2, "dental", "call.score", A_SCORE, "CA_1")),
        usage_row(metered(3, "taller", "call.summary", a_summary([LLM]), "CA_2")),
        usage_row(metered(4, "dental", "call.summary", a_summary([]), "CA_3")),
    ]
    totals = totals_by_org(rows)
    assert list(totals) == ["dental", "taller"]
    assert (totals["dental"].calls, totals["dental"].judge_calls, totals["dental"].minutes) == (
        2,
        3,
        4.0,
    )
    assert (totals["dental"].messages, totals["taller"].input_tokens) == (16, 900)
    assert (totals["dental"].evals, totals["taller"].evals) == (2, 0)


def test_the_metered_types_are_the_summary_the_score_and_a_try_and_nothing_else() -> None:
    assert METERED_TYPES == ("call.summary", "call.score", "evals.spent")


def test_a_summary_whose_call_ran_on_the_boxs_key_counts_its_minutes_as_lent_and_one_on_its_own_keys_none() -> None:
    lent = lent_row(usage_row(metered(1, "dental", "call.summary", a_summary([STT]), "CA_1")), ("deepgram", "google"))
    own = lent_row(usage_row(metered(2, "dental", "call.summary", a_summary([STT]), "CA_2")), ())
    assert (lent.lent, lent.used.minutes, lent.used.lent_minutes) == (("deepgram", "google"), 2.0, 2.0)
    assert (own.lent, own.used.minutes, own.used.lent_minutes) == ((), 2.0, 0.0)
    assert totals_by_org([lent, own])["dental"].lent_minutes == 2.0
