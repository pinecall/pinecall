"""Tests for what a golden expects at the end of its call: each check settled by code, or asked of a judge it names."""

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.evals.service.goldens import Check, Settled, list_checks, score_golden
from runtime.evals.service.matrix import Ruling
from runtime.judging import service as judging
from runtime.judging.service import judges as roster
from runtime.wire.goldens import Golden
from tests.conftest import Tenant, needs_the_database
from tests.judging.factories import (
    THE_CLINIC,
    WHEN,
    a_log,
    a_transcript,
    agent,
    agent_line,
    answering,
    caller,
    caller_line,
    logged_call,
    with_no_gate,
)

NOBODY: Mapping[str, judging.RosterJudge] = {}


def expecting(**expect: object) -> Golden:
    """A golden of one line that expects this."""
    return Golden.model_validate({"name": "g", "turns": [{"say": "hola"}], "expect": expect})


def check_named(checks: list[Check], name: str) -> Check:
    """The check of that name among these."""
    return next(check for check in checks if check.name == name)


def settled(golden: Golden, transcript: judging.Transcript, name: str) -> Ruling:
    """What the golden's check of that name came to on the call, by code alone."""
    check = check_named(list_checks(golden, transcript, NOBODY), name)
    assert isinstance(check, Settled), f"{name} was not settled by code"
    return check.ruling


# ── what a golden expects at the end ──


def test_the_checks_come_in_the_order_expect_names_them_and_none_unasked() -> None:
    transcript = a_transcript(caller_line("hola"))
    golden = expecting(says=["45"], says_any=["sí"], **{"not": ["gratis"]}, tools=["find"], register="usted")
    assert [check.name for check in list_checks(golden, transcript, NOBODY)] == [
        "tools",
        "silence",
        "says",
        "says_any",
        "register",
    ]


@needs_the_database
async def test_a_hang_up_judge_a_golden_names_is_asked_of_its_call_from_the_roster(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, agent: str
) -> None:
    model = answering(
        {"name": "submit_applies", "arguments": {"applies": True, "reason": "a call back"}},
        {"name": "submit_verdict", "arguments": {"verdict": "broken", "reason": "nobody booked"}},
    )
    async with sessions() as session:
        every = {judge.spec.name: judge for judge in await roster.roster_of(session, tenant.org, agent)}
    transcript = a_transcript(caller_line("hola"), agent_line("Le llamaremos mañana."))
    checks = list_checks(expecting(judges=["promises", "consent"]), transcript, every)
    assert [check.name for check in checks] == ["promises", "consent"]
    (score,) = await score_golden([check_named(checks, "promises")], transcript, judging.Context(), model)
    assert not score.passed
    assert len(model.requests) == 2, "its trigger, then its question"


def test_a_judge_the_roster_does_not_hold_breaks_the_golden_and_names_the_roster() -> None:
    result = settled(expecting(judges=["persona"]), a_transcript(caller_line("hola")), "persona")
    assert not result.passed
    assert result.reason == "this golden asks persona, and there is no such judge: there are no judge at all"


def test_a_golden_that_expects_nothing_at_the_end_is_held_to_nothing_there() -> None:
    golden = Golden.model_validate({"name": "g", "turns": [{"say": "hola"}]})
    assert list_checks(golden, a_transcript(), NOBODY) == []


async def test_a_conversation_that_called_every_named_tool_holds_without_a_judge() -> None:
    transcript = a_transcript(
        caller_line(WHEN),
        agent_line("Le busco un hueco.", calls=(logged_call("find_slots", {}, "[]"),)),
    )
    checks = list_checks(expecting(tools=["find_slots"]), transcript, NOBODY)
    (score,) = await score_golden(checks, transcript, judging.Context(), None)
    assert (score.metric, score.passed, score.judge_calls) == ("tools", True, 0)


def test_a_tool_the_golden_named_and_nobody_called_is_named_in_the_reason() -> None:
    transcript = a_transcript(
        caller_line(WHEN),
        agent_line("Le busco un hueco.", calls=(logged_call("find_slots", {}, "[]"),)),
    )
    result = settled(expecting(tools=["book"]), transcript, "tools")
    assert not result.passed
    assert "book" in result.reason
    assert "find_slots" in result.reason


def test_a_conversation_that_called_nothing_says_so_rather_than_listing_nothing() -> None:
    transcript = a_transcript(caller_line(WHEN), agent_line("No sé."))
    assert "no tool at all" in settled(expecting(tools=["find"]), transcript, "tools").reason


# Consent is the judge model's to answer; not_tools catches the booking by code, asking nobody.
def test_a_forbidden_tool_that_ran_is_caught_with_the_seq_the_log_gave_it() -> None:
    transcript = judging.transcript_of(with_no_gate(), THE_CLINIC)
    result = settled(expecting(not_tools=["book_appointment"]), transcript, "not_tools")
    assert result.reason == "the golden forbids book_appointment, and this call ran book_appointment at seq 3"


def test_a_call_that_kept_off_the_forbidden_tool_holds_and_asks_nobody() -> None:
    transcript = judging.transcript_of(with_no_gate(), THE_CLINIC)
    result = settled(expecting(not_tools=["transfer"]), transcript, "not_tools")
    assert result.passed
    assert "none of the 1 forbidden tool(s) ran" in result.reason


def test_the_phrases_hold_on_the_very_call_the_forbidden_tool_check_breaks() -> None:
    log = a_log(
        caller("Me viene bien la de las cuatro."),
        ("tool.call", {"call_id": "c1", "name": "book", "arguments": {}, "speech_id": "sp_9"}),
        agent("Voy a reservarle la cita. Le llega un SMS con la confirmación."),
    )
    transcript = judging.transcript_of(log, None)
    golden = expecting(**{"not": ["queda reservada", "he reservado", "está reservada"]}, not_tools=["book"])
    assert settled(golden, transcript, "silence").passed
    assert not settled(golden, transcript, "not_tools").passed


def test_a_phrase_is_found_in_whichever_turn_the_agent_put_it_in() -> None:
    transcript = a_transcript(caller_line("hola"), agent_line("Un momento."), agent_line("A las 10:15."))
    assert settled(expecting(says=["10:15"]), transcript, "says").passed


def test_a_phrase_is_matched_the_way_a_person_reads_it_and_not_by_case() -> None:
    transcript = a_transcript(caller_line("hola"), agent_line("La consulta cuesta 45 Euros."))
    assert settled(expecting(says=["45 euros"]), transcript, "says").passed


def test_a_phrase_the_agent_never_said_names_itself_in_the_reason() -> None:
    transcript = a_transcript(caller_line("hola"), agent_line("Cuesta 45 euros."))
    result = settled(expecting(says=["gratis"]), transcript, "says")
    assert not result.passed
    assert "'gratis'" in result.reason


def test_an_expectation_with_several_right_answers_holds_on_any_one_of_them() -> None:
    transcript = a_transcript(caller_line("¿Abren el sábado?"), agent_line("Sí, de nueve a DOS."))
    accepted = ["de 9 a 14", "de nueve a dos", "por la mañana"]
    result = settled(expecting(says_any=accepted), transcript, "says_any")
    assert result.passed
    assert "'de nueve a dos'" in result.reason


def test_an_expectation_none_of_whose_answers_was_said_names_every_one() -> None:
    transcript = a_transcript(caller_line("¿Abren el sábado?"), agent_line("No lo sé."))
    result = settled(expecting(says_any=["de 9 a 14", "por la mañana"]), transcript, "says_any")
    assert not result.passed
    assert "'de 9 a 14', 'por la mañana'" in result.reason


def test_a_forbidden_phrase_is_caught_and_the_turn_that_said_it_is_named() -> None:
    transcript = a_transcript(caller_line("hola"), agent_line("Un momento."), agent_line("La primera es gratis."))
    assert "'gratis' in agent turn 2" in settled(expecting(**{"not": ["gratis"]}), transcript, "silence").reason


def test_silence_holds_when_none_of_the_forbidden_phrases_was_said() -> None:
    transcript = a_transcript(caller_line("hola"), agent_line("Cuesta 45 euros."))
    assert settled(expecting(**{"not": ["gratis"]}), transcript, "silence").passed


# ── the register ──


def register_of(reply: str, expected: str) -> Ruling:
    transcript = a_transcript(caller_line("Hola, quería una cita."), agent_line(reply))
    return settled(expecting(register=expected), transcript, "register")


def test_an_agent_asked_for_usted_that_keeps_it_holds_without_a_judge() -> None:
    assert register_of("Claro, usted dirá. ¿Su nombre?", "usted").passed


def test_an_agent_asked_for_usted_that_tutea_is_caught_word_by_word() -> None:
    result = register_of("Vale, dime tu nombre.", "usted")
    assert "'tu' in agent turn 1" in result.reason
    assert "asked for usted" in result.reason


def test_an_agent_asked_for_tu_that_slips_into_usted_is_caught_too() -> None:
    assert not register_of("Cuando usted quiera.", "tu").passed


def test_a_turn_that_marks_neither_register_is_not_a_slip() -> None:
    assert register_of("Un momento, lo compruebo.", "usted").passed


def test_a_word_that_only_contains_a_marker_is_not_the_marker() -> None:
    assert register_of("Le paso con el tutor del paciente.", "usted").passed


def test_the_ambiguous_third_person_words_are_left_out_on_purpose() -> None:
    assert register_of("Le confirmo su cita.", "tu").passed
