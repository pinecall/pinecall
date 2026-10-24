"""The org's dataset: a finished call made a golden, born at hang-up, decided by a person, played again."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.enums import CaseSource, CaseStatus, Env
from pinecall_runtime.exceptions import Conflict, NotFound, ValidationError
from pinecall_runtime.judging.schemas import BrokeOn, CaseDecision, CaseRow
from pinecall_runtime.judging.service import cases, groups
from pinecall_runtime.judging.service.cases import Born, Promoted, cut_at, expect_of, golden_of
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.goldens import Expect, Golden, Turn
from pinecall_runtime.wire.scores import CallScore, Judgment, JudgmentEvidence
from tests.conftest import Tenant, needs_the_database
from tests.judging.factories import AGENT, BOOK, CALL, a_log, agent, before_the_yes, caller


def a_score(*judgments: Judgment) -> CallScore:
    """A call.score of these verdicts."""
    passed = not any(judgment.verdict == "broken" for judgment in judgments)
    return CallScore(judges=list(judgments), judge_calls=0, passed=passed)


def breaking(name: str, *, seqs: list[int] | None = None) -> Judgment:
    """A judge that broke."""
    return Judgment(
        name=name, verdict="broken", criteria="", reason="it broke", evidence=JudgmentEvidence(seqs=seqs or [])
    )


def holding(name: str) -> Judgment:
    """A judge that held."""
    return Judgment(name=name, verdict="held", criteria="", reason="it held", evidence=JudgmentEvidence(seqs=[]))


def a_call(number: int) -> list[Entry]:
    """Another call that broke, its caller's own words, its own id."""
    return [
        line.model_copy(update={"call": f"CA_{number:06d}"})
        for line in a_log(caller(f"Llamada número {number}"), agent("Le llamaremos."))
    ]


# ── a call made a golden ──


def test_a_golden_is_the_callers_lines_and_the_apps_facts_as_turns_and_its_first_state() -> None:
    """The caller's lines and the app's events play again; a participant's click and silence do not."""
    log = a_log(
        ("state.changed", {"state": {"stage": "book"}, "changed": ["stage"]}),
        caller("Quiero el jueves"),
        ("event.received", {"name": "slot_freed", "data": {"at": "10:15"}, "source": "app"}),
        ("event.received", {"name": "clicked", "data": {}, "source": "participant"}),
        agent("Se liberó el de las 10:15."),
        ("state.changed", {"state": {"stage": "confirm"}, "changed": ["stage"]}),
        caller("Vale"),
        caller("   "),
    )
    golden = golden_of(log, "jueves", Expect(says=["10:15"]))
    played = [turn.say or (turn.event and turn.event.name) for turn in golden.turns]
    assert played == ["Quiero el jueves", "slot_freed", "Vale"]
    assert (golden.state, golden.promoted_from, golden.expect.says) == ({"stage": "book"}, CALL, ["10:15"])
    assert golden.today is not None
    bare = golden_of(a_log(caller("Hola")), "hola", Expect()).dump()
    assert set(bare) == {"name", "turns", "today", "expect", "promoted_from"}, "nothing empty is written"


def test_what_the_call_recalled_rides_the_golden_so_a_replay_knows_what_the_call_knew() -> None:
    """Facts memory handed the call are the golden's memory, once."""
    recalled: JsonObject = {
        "ops": [
            {
                "op": "recall",
                "contact": "+34600000001",
                "facts": [{"id": "f1", "text": "Prefiere mañanas", "source": "CA_1"}],
                "took_ms": 3.0,
            }
        ]
    }
    log = a_log(caller("¿El martes?"), ("memory.ops", recalled), ("memory.ops", recalled))
    assert golden_of(log, "martes", Expect()).memory == ["Prefiere mañanas"]


def test_a_broken_verdict_says_what_must_not_happen_again_and_a_model_judge_is_named() -> None:
    """Consent becomes the tool it broke on, grounded a field, a model judge asked again by name."""
    log = before_the_yes()
    booked = next(entry.seq for entry in log if entry.type == "tool.call")
    score = a_score(
        breaking("consent", seqs=[booked]),
        breaking("grounded"),
        breaking("promises"),
        breaking("expected-outcome"),
        holding("disclosed"),
    )
    assert expect_of(score.judges, log).dump() == {"not_tools": [BOOK.name], "grounded": True, "judges": ["promises"]}
    assert expect_of(a_score(breaking("promises")).judges, log).dump() == {"judges": ["promises"]}


def test_a_call_cut_at_a_seq_opens_in_the_state_it_was_in_there_and_plays_what_came_after() -> None:
    """Cut at 3, the golden opens in stage book; cut at 0, it is the whole call."""
    log = a_log(
        ("state.changed", {"state": {"stage": "identify"}, "changed": ["stage"]}),
        caller("Soy Marta"),
        ("state.changed", {"state": {"stage": "book"}, "changed": ["stage"]}),
        caller("El jueves"),
    )
    golden = golden_of(cut_at(log, 3), "jueves", Expect())
    assert (golden.state, [turn.say for turn in golden.turns]) == ({"stage": "book"}, ["El jueves"])
    assert [turn.say for turn in golden_of(cut_at(log, 0), "todo", Expect()).turns] == ["Soy Marta", "El jueves"]


def test_a_call_whose_caller_said_nothing_is_no_case() -> None:
    """With no line of the caller's there is nothing to play again."""
    with pytest.raises(Conflict, match="no line of the caller's"):
        golden_of(a_log(agent("¿Hola?")), "silence", Expect())


def test_a_judge_called_wrong_is_one_that_broke_and_a_note_needs_one() -> None:
    """judge_was_wrong dismisses, names a judge that broke, and carries the note."""
    case = CaseRow.model_validate(
        {
            "id": "case_1",
            "agent": AGENT,
            "name": "promises-x",
            "golden": {"name": "promises-x", "turns": [{"say": "Hola"}]},
            "source_call": "CA_1",
            "source_env": "production",
            "held_out": False,
            "author": cases.THE_PANEL,
            "created_at": datetime(2026, 9, 30, tzinfo=UTC),
            "broke": [BrokeOn(judge="promises", reason="it broke").dump()],
        }
    )
    cases.check_decision(case, CaseDecision(status=CaseStatus.dismissed, judge_was_wrong="promises"))
    with pytest.raises(ValidationError, match="send it with status dismissed"):
        cases.check_decision(case, CaseDecision(status=CaseStatus.approved, judge_was_wrong="promises"))
    with pytest.raises(ValidationError, match="send judge_was_wrong"):
        cases.check_decision(case, CaseDecision(status=CaseStatus.dismissed, note="it did book"))
    with pytest.raises(ValidationError, match="did not break on grounded"):
        cases.check_decision(case, CaseDecision(status=CaseStatus.dismissed, judge_was_wrong="grounded"))


# ── kept, picked, decided, forgotten ──


@needs_the_database
async def test_a_case_is_kept_once_by_name_and_a_run_picks_what_is_not_held_out(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A name is the agent's once; the nightly skips held-out cases, a release names them."""
    golden = golden_of(a_log(caller("Hola")), "hola", Expect())
    async with sessions.begin() as session:
        kept = await cases.promote_case(session, golden, AGENT, Promoted(tenant.org, Env.production, "hola", "m_ana"))
        await cases.promote_case(
            session, golden, AGENT, Promoted(tenant.org, Env.production, "held", "m_ana", held_out=True)
        )
        with pytest.raises(Conflict, match="named hola already"):
            await cases.promote_case(session, golden, AGENT, Promoted(tenant.org, Env.sandbox, "hola", "m_bo"))
    assert (kept.source_call, kept.source_env, kept.author) == (CALL, Env.production, "m_ana")
    async with sessions() as session:
        nightly = await cases.pick_cases(session, tenant.org, AGENT, [], every=True)
        release = await cases.pick_cases(session, tenant.org, AGENT, ["held"], every=True)
        with pytest.raises(NotFound, match="no case named nobody"):
            await cases.pick_cases(session, tenant.org, AGENT, ["nobody"], every=False)
        listed = await cases.list_cases(session, tenant.org, None)
    assert [golden.name for golden in nightly] == ["hola"]
    assert [golden.name for golden in release] == ["held", "hola"]
    assert [case.name for case in listed] == ["held", "hola"]
    async with sessions.begin() as session:
        with pytest.raises(NotFound):
            await cases.delete_case(session, "another-org", kept.id)
        await cases.delete_case(session, tenant.org, kept.id)
        with pytest.raises(NotFound):
            await cases.delete_case(session, tenant.org, kept.id)


@needs_the_database
async def test_a_call_a_judge_broke_on_waits_as_a_pending_case_once_until_the_inbox_is_full(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A broken call is kept once, named by its judge and words; past the cap nothing more is kept."""
    born = Born(tenant.org, Env.production, AGENT, version=4)
    score = a_score(breaking("promises"))
    log = a_log(caller("¿Me llaman mañana, por favor?"), agent("Le llamaremos mañana."))
    async with sessions.begin() as session:
        await cases.keep_at_hangup(session, log, score, born)
        await cases.keep_at_hangup(session, log, score, born)
        await cases.keep_at_hangup(session, log, a_score(holding("promises")), born)
    async with sessions() as session:
        (case,) = await cases.list_cases(session, tenant.org, AGENT, CaseStatus.pending)
    assert case.name == "promises-me-llaman-manana-por-8f4a2c"
    assert (case.author, case.source_version, case.status) == (cases.THE_PANEL, 4, CaseStatus.pending)
    assert [(judgment.judge, judgment.reason) for judgment in case.broke] == [("promises", "it broke")]
    assert case.golden.expect.judges == ["promises"]
    async with sessions.begin() as session:
        for number in range(cases.PENDING_AT_MOST):
            await cases.keep_at_hangup(session, a_call(number), score, born)
    async with sessions() as session:
        assert await cases.waiting_cases(session, tenant.org, AGENT) == cases.PENDING_AT_MOST


@needs_the_database
async def test_a_simulation_a_judge_broke_on_is_kept_with_its_persona_in_the_judges_group(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A persona's call is a simulation, grouped with the person's calls its judge broke on."""
    started: JsonObject = {
        "channel": "web",
        "direction": "inbound",
        "from": "simulated_caller",
        "to": AGENT,
        "caller": None,
        "started_at": 1.0,
        "persona": "apurado",
    }
    born = Born(tenant.org, Env.sandbox, AGENT, None)
    async with sessions.begin() as session:
        await cases.keep_at_hangup(
            session, a_log(("call.started", started), caller("Hola")), a_score(breaking("promises")), born
        )
        await cases.keep_at_hangup(session, a_call(1), a_score(breaking("promises")), born)
    async with sessions() as session:
        person, simulation = sorted(await cases.list_cases(session, tenant.org, AGENT), key=lambda case: case.source)
    assert (person.source, simulation.source, simulation.persona) == (CaseSource.call, CaseSource.simulation, "apurado")
    assert simulation.group is not None
    assert simulation.group == person.group


@needs_the_database
async def test_a_person_decides_a_case_and_the_nightly_plays_only_what_was_approved(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Approved plays nightly, dismissed never, pending by name; one kept in the repo leaves the nightly."""
    born = Born(tenant.org, Env.production, AGENT, None)
    async with sessions.begin() as session:
        for number in range(3):
            await cases.keep_at_hangup(session, a_call(number), a_score(breaking("promises")), born)
    async with sessions.begin() as session:
        first, second, third = await cases.list_cases(session, tenant.org, AGENT, CaseStatus.pending)
        approved = await cases.decide_case(
            session, tenant.org, first.id, CaseDecision(status=CaseStatus.approved), by="m_ana"
        )
        dismissed = await cases.decide_case(
            session, tenant.org, second.id, CaseDecision(status=CaseStatus.dismissed), by="m_ana"
        )
    assert (approved.status, approved.decided_by) == (CaseStatus.approved, "m_ana")
    with pytest.raises(Conflict, match="is already dismissed"):
        cases.check_decision(dismissed, CaseDecision(status=CaseStatus.dismissed))
    async with sessions() as session:
        assert await cases.waiting_cases(session, tenant.org, AGENT) == 1
        nightly = await cases.pick_cases(session, tenant.org, AGENT, [], every=True)
        named = await cases.pick_cases(session, tenant.org, AGENT, [third.name], every=False)
    assert [golden.name for golden in nightly] == [first.name]
    assert [golden.name for golden in named] == [third.name], "a pending case is reproduced by name"
    in_the_repo = CaseDecision(kept_in_repo=True)
    async with sessions.begin() as session:
        await cases.decide_case(session, tenant.org, first.id, in_the_repo, by="m_ana")
        assert await cases.pick_cases(session, tenant.org, AGENT, [], every=True) == []
        with pytest.raises(NotFound):
            await cases.decide_case(session, "another-org", first.id, in_the_repo, by="m_ana")


@needs_the_database
async def test_a_person_writes_a_case_by_hand_writes_it_again_and_never_over_a_calls(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Written approved with no call; the same name rewrites the golden and keeps the rest; a call's name is refused."""
    golden = Golden(
        name="ignored", turns=[Turn(say="¿Cuánto cuesta una resonancia?")], expect=Expect.model_validate({"not": ["€"]})
    )
    writing = Promoted(tenant.org, Env.sandbox, "no-dice-un-precio", "m_ana")
    async with sessions.begin() as session:
        written = await cases.write_case(session, golden, AGENT, writing)
    assert (written.name, written.golden.name) == ("no-dice-un-precio", "no-dice-un-precio")
    assert (written.source, written.status, written.source_call, written.broke) == (
        CaseSource.person,
        CaseStatus.approved,
        None,
        [],
    )
    again = golden.model_copy(update={"expect": Expect.model_validate({"not": ["€", "euros"]})})
    async with sessions.begin() as session:
        rewritten = await cases.write_case(
            session, again, AGENT, Promoted(tenant.org, Env.sandbox, written.name, "m_bo")
        )
    assert (rewritten.id, rewritten.author, rewritten.golden.expect.not_said) == (written.id, "m_ana", ["€", "euros"])
    async with sessions.begin() as session:
        await cases.keep_at_hangup(
            session, a_call(1), a_score(breaking("promises")), Born(tenant.org, Env.sandbox, AGENT, None)
        )
        (born,) = await cases.list_cases(session, tenant.org, AGENT, CaseStatus.pending)
        with pytest.raises(Conflict, match="not written by hand"):
            await cases.write_case(session, golden, AGENT, Promoted(tenant.org, Env.sandbox, born.name, "m_ana"))
    async with sessions() as session:
        nightly = await cases.pick_cases(session, tenant.org, AGENT, [], every=True)
    assert [one.name for one in nightly] == ["no-dice-un-precio"]
    with pytest.raises(ValidationError, match="a person kept it"):
        cases.check_decision(rewritten, CaseDecision(status=CaseStatus.dismissed, judge_was_wrong="grounded"))


# E (2026-10-23): a group whose cases a person approved one by one stayed pending, first of `cases groups`.
@needs_the_database
async def test_a_group_decided_case_by_case_is_decided_once_nothing_in_it_waits(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    born = Born(tenant.org, Env.production, AGENT, None)
    async with sessions.begin() as session:
        for number in range(2):
            await cases.keep_at_hangup(session, a_call(number), a_score(breaking("promises")), born)
    async with sessions.begin() as session:
        first, second = await cases.list_cases(session, tenant.org, AGENT, CaseStatus.pending)
        await cases.decide_case(session, tenant.org, first.id, CaseDecision(status=CaseStatus.dismissed), by="m_ana")
    async with sessions() as session:
        [group] = await groups.list_groups(session, tenant.org, AGENT)
    assert group.status == CaseStatus.pending, "one case still waits"
    async with sessions.begin() as session:
        await cases.decide_case(session, tenant.org, second.id, CaseDecision(status=CaseStatus.approved), by="m_ana")
    async with sessions() as session:
        [group] = await groups.list_groups(session, tenant.org, AGENT)
    assert (group.status, group.cases) == (CaseStatus.approved, 2)
