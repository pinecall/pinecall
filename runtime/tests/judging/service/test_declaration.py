"""A class's judges and personas: the library's switches, its own by sentence, and what a PUT refuses refused."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import THE_ORGS_OWN
from runtime.agents.declaration import Declaration
from runtime.enums import JudgeAnswer
from runtime.exceptions import Conflict, NotFound, ServiceUnavailable, ValidationError
from runtime.judging.service import judges, library, personas
from runtime.judging.service.declaration import check_declaration, check_personas_of_class
from runtime.judging.service.judges import judge_named, judges_of_class, put_judge, roster_of, spec_of
from runtime.judging.service.personas import persona_named, persona_of, personas_of_class, put_persona
from runtime.providers.service import Keyring
from runtime.wire.declaration import JudgeDeclaration, JudgesDeclared, PersonaDeclaration, PersonasDeclared
from tests.conftest import Tenant, configured, needs_the_database

AGENT = "front-desk"
OFFERS = JudgeDeclaration(name="offers-next-slot", question="Did the agent offer the next free slot?")
IN_A_RUSH = PersonaDeclaration(name="in-a-rush", goal="book today", style="short, interrupts")


def test_the_switches_are_the_names_on_and_every_other_of_the_library_off() -> None:
    """A class that names `consent` alone runs `consent` and none of Pinecall's others."""
    switches, own = judges_of_class(JudgesDeclared(on=["consent"], own=[OFFERS]))
    assert switches["consent"] is True
    assert not any(on for name, on in switches.items() if name != "consent")
    assert set(switches) == set(library.library_judges())
    assert [spec.name for spec in own] == ["offers-next-slot"]
    assert own[0].answer is JudgeAnswer.verdict and own[0].reads == frozenset()


def test_an_empty_declaration_is_the_whole_library_off_and_nothing_of_its_own() -> None:
    switches, own = judges_of_class(JudgesDeclared())
    assert not any(switches.values()) and own == ()
    played, callers = personas_of_class(PersonasDeclared())
    assert not any(played.values()) and callers == ()


def test_a_name_that_is_none_of_the_librarys_is_refused_naming_the_list() -> None:
    with pytest.raises(ValidationError, match="offers-next-slot is none of Pinecall's judges: `pinecall judges list`"):
        judges_of_class(JudgesDeclared(on=["offers-next-slot"]))
    with pytest.raises(ValidationError, match="nobody is none of Pinecall's personas: `pinecall personas list`"):
        personas_of_class(PersonasDeclared(on=["nobody"]))


def test_a_judge_of_ones_own_under_a_library_name_is_refused_towards_the_switch() -> None:
    taken = JudgeDeclaration(name="consent", question="Did the caller agree?")
    towards = "consent is one of Pinecall's judges: switch it on in the class's `judges`"
    with pytest.raises(ValidationError, match=towards):
        judges_of_class(JudgesDeclared(own=[taken]))
    rush = PersonaDeclaration(name="in-a-hurry", goal="book", style="fast")
    with pytest.raises(ValidationError, match="in-a-hurry is one of Pinecall's personas"):
        personas_of_class(PersonasDeclared(own=[rush]))


def test_two_of_one_name_are_refused() -> None:
    with pytest.raises(ValidationError, match="the class declares two judges called offers-next-slot"):
        judges_of_class(JudgesDeclared(own=[OFFERS, OFFERS]))
    with pytest.raises(ValidationError, match="the class declares two personas called in-a-rush"):
        personas_of_class(PersonasDeclared(own=[IN_A_RUSH, IN_A_RUSH]))


def test_a_judge_or_a_persona_is_held_to_what_a_put_holds_it_to() -> None:
    """The same sentences a PUT gives: no question, a choice with one answer, no goal, a name that is none."""
    with pytest.raises(ValidationError, match="a judge asks a question of a call"):
        judges_of_class(JudgesDeclared(own=[JudgeDeclaration(name="empty", question=" ")]))
    one = JudgeDeclaration(name="which", question="Which?", answer=JudgeAnswer.choice, choices=["a"])
    with pytest.raises(ValidationError, match="at least two choices"):
        judges_of_class(JudgesDeclared(own=[one]))
    with pytest.raises(ValidationError, match="a persona wants something"):
        personas_of_class(PersonasDeclared(own=[PersonaDeclaration(name="mute", goal="", style="x")]))
    with pytest.raises(ValidationError, match="'Not A Name' is not a persona's name"):
        personas_of_class(PersonasDeclared(own=[PersonaDeclaration(name="Not A Name", goal="g", style="s")]))


def test_a_persona_on_a_vendor_the_box_lacks_or_nobody_keyed_is_refused_at_configure() -> None:
    """What a PUT refuses of a caller's model and voice is refused when the class declares the caller."""
    lacking = PersonaDeclaration(name="on-nothing", goal="g", style="s", tts="nonvendor")
    with pytest.raises(ValidationError, match="no vendor named 'nonvendor'"):
        check_personas_of_class(configured(), Keyring(), PersonasDeclared(own=[lacking]))
    unkeyed = PersonaDeclaration(name="unkeyed", goal="g", style="s", llm="openai/gpt-5.4-mini")
    with pytest.raises(ServiceUnavailable, match="openai has no key: the org brought none and the box holds none"):
        check_personas_of_class(configured(), Keyring(), PersonasDeclared(own=[unkeyed]))
    check_personas_of_class(configured(), Keyring(), PersonasDeclared(own=[IN_A_RUSH]))


@needs_the_database
async def test_a_judge_the_org_wrote_under_the_name_is_refused_as_the_orgs(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """One name is one question per call: the org's judge under it stands, and the class's is refused."""
    spec = spec_of("offers-next-slot", judges.Wanted(question="Did it offer a slot?"))
    async with sessions.begin() as session:
        await put_judge(session, tenant.org, THE_ORGS_OWN, spec, by="m_ana")
    config = Declaration(slug=AGENT, judges=JudgesDeclared(own=[OFFERS]))
    async with sessions.begin() as session:
        with pytest.raises(Conflict, match="offers-next-slot is the org's judge already"):
            await check_declaration(session, configured(), Keyring(), tenant.org, AGENT, config)
        free = OFFERS.model_copy(update={"name": "offers-a-slot"})
        other = Declaration(slug=AGENT, judges=JudgesDeclared(own=[free]), personas=PersonasDeclared(own=[IN_A_RUSH]))
        await check_declaration(session, configured(), Keyring(), tenant.org, AGENT, other)


# ── read as the class's: the panel and the roster ──


@needs_the_database
async def test_the_panel_is_the_class_s_switches_and_own_with_the_orgs_own_and_never_the_agents_rows(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Declared, the class is the agent's list; the org's own judges meet its calls on top; the rows are not read."""
    async with sessions.begin() as session:
        the_orgs = spec_of("polite", judges.Wanted(question="Polite?"))
        await put_judge(session, tenant.org, THE_ORGS_OWN, the_orgs, by="m_ana")
        a_row = spec_of("from-a-row", judges.Wanted(question="Written in the console?"))
        await put_judge(session, tenant.org, AGENT, a_row, by="m_ana")
        roster = await roster_of(session, tenant.org, AGENT, JudgesDeclared(on=["grounded"], own=[OFFERS]))
        assert [(judge.spec.name, judge.owner) for judge in roster if judge.owner != judges.PINECALL] == [
            ("polite", judges.THE_ORG),
            ("offers-next-slot", judges.THE_CLASS),
        ]
        switched = {judge.spec.name: judge.on for judge in roster if judge.owner == judges.PINECALL}
        assert switched["grounded"] and not switched["consent"]
        named = await judge_named(session, tenant.org, AGENT, "offers-next-slot", JudgesDeclared(own=[OFFERS]))
        assert named == spec_of("offers-next-slot", OFFERS)
        with pytest.raises(NotFound, match=f"{AGENT} has no judge called from-a-row"):
            await judge_named(session, tenant.org, AGENT, "from-a-row", JudgesDeclared(own=[OFFERS]))
        # Nothing declared: the rows, as before.
        rows = await roster_of(session, tenant.org, AGENT, None)
        assert [judge.spec.name for judge in rows if judge.owner != judges.PINECALL] == ["polite", "from-a-row"]


@needs_the_database
async def test_a_persona_is_the_class_s_own_by_name_else_pinecalls_and_never_the_agents_row(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Declared, the roster is the class's: its own by name, Pinecall's by name as the org plays them, no row."""
    async with sessions.begin() as session:
        a_row = persona_of("from-a-row", personas.Wanted(goal="g", style="s"))
        await put_persona(session, tenant.org, AGENT, a_row, by="m_ana", was=None)
        declared = PersonasDeclared(own=[IN_A_RUSH])
        found = await persona_named(session, tenant.org, AGENT, "in-a-rush", declared)
        assert found is not None and found.goal == "book today"
        library = await persona_named(session, tenant.org, AGENT, "in-a-hurry", declared)
        assert library is not None and library.name == "in-a-hurry"
        assert await persona_named(session, tenant.org, AGENT, "from-a-row", declared) is None
        row = await persona_named(session, tenant.org, AGENT, "from-a-row", None)
        assert row is not None and row.name == "from-a-row"
