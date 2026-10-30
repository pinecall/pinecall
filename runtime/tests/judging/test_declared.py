"""A class's judges and personas: the library's switches, its own by sentence, and what a PUT refuses refused."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.enums import JudgeAnswer
from pinecall_runtime.exceptions import Conflict, ServiceUnavailable, ValidationError
from pinecall_runtime.judging.schemas import JudgeRequest
from pinecall_runtime.judging.service import catalog
from pinecall_runtime.judging.service.declared import (
    check_declared,
    check_declared_personas,
    declared_judges,
    declared_personas,
)
from pinecall_runtime.judging.service.judges import put_judge, spec_of
from pinecall_runtime.kit.auth import THE_ORGS_OWN
from pinecall_runtime.providers.service import Keyring
from pinecall_runtime.wire.parts import (
    JudgeDeclaration,
    JudgesDeclared,
    PersonaDeclaration,
    PersonasDeclared,
)
from tests.conftest import Tenant, configured, needs_the_database

AGENT = "front-desk"
OFFERS = JudgeDeclaration(name="offers-next-slot", question="Did the agent offer the next free slot?")
IN_A_RUSH = PersonaDeclaration(name="in-a-rush", goal="book today", style="short, interrupts")


def test_the_switches_are_the_names_on_and_every_other_of_the_library_off() -> None:
    """A class that names `consent` alone runs `consent` and none of Pinecall's others."""
    switches, own = declared_judges(JudgesDeclared(on=["consent"], own=[OFFERS]))
    assert switches["consent"] is True
    assert not any(on for name, on in switches.items() if name != "consent")
    assert set(switches) == set(catalog.library_judges())
    assert [spec.name for spec in own] == ["offers-next-slot"]
    assert own[0].answer is JudgeAnswer.verdict and own[0].reads == ()


def test_an_empty_declaration_is_the_whole_library_off_and_nothing_of_its_own() -> None:
    switches, own = declared_judges(JudgesDeclared())
    assert not any(switches.values()) and own == ()
    played, callers = declared_personas(PersonasDeclared())
    assert not any(played.values()) and callers == ()


def test_a_name_that_is_none_of_the_librarys_is_refused_naming_the_list() -> None:
    with pytest.raises(ValidationError, match="offers-next-slot is none of Pinecall's judges: `pinecall judges list`"):
        declared_judges(JudgesDeclared(on=["offers-next-slot"]))
    with pytest.raises(ValidationError, match="nobody is none of Pinecall's personas: `pinecall personas list`"):
        declared_personas(PersonasDeclared(on=["nobody"]))


def test_a_judge_of_ones_own_under_a_library_name_is_refused_towards_the_switch() -> None:
    taken = JudgeDeclaration(name="consent", question="Did the caller agree?")
    towards = "consent is one of Pinecall's judges: switch it on in the class's `judges`"
    with pytest.raises(ValidationError, match=towards):
        declared_judges(JudgesDeclared(own=[taken]))
    rush = PersonaDeclaration(name="in-a-hurry", goal="book", style="fast")
    with pytest.raises(ValidationError, match="in-a-hurry is one of Pinecall's personas"):
        declared_personas(PersonasDeclared(own=[rush]))


def test_two_of_one_name_are_refused() -> None:
    with pytest.raises(ValidationError, match="the class declares two judges called offers-next-slot"):
        declared_judges(JudgesDeclared(own=[OFFERS, OFFERS]))
    with pytest.raises(ValidationError, match="the class declares two personas called in-a-rush"):
        declared_personas(PersonasDeclared(own=[IN_A_RUSH, IN_A_RUSH]))


def test_a_judge_or_a_persona_is_held_to_what_a_put_holds_it_to() -> None:
    """The same sentences a PUT gives: no question, a choice with one answer, no goal, a name that is none."""
    with pytest.raises(ValidationError, match="a judge asks a question of a call"):
        declared_judges(JudgesDeclared(own=[JudgeDeclaration(name="empty", question=" ")]))
    one = JudgeDeclaration(name="which", question="Which?", answer=JudgeAnswer.choice, choices=["a"])
    with pytest.raises(ValidationError, match="at least two choices"):
        declared_judges(JudgesDeclared(own=[one]))
    with pytest.raises(ValidationError, match="a persona wants something"):
        declared_personas(PersonasDeclared(own=[PersonaDeclaration(name="mute", goal="", style="x")]))
    with pytest.raises(ValidationError, match="'Not A Name' is not a persona's name"):
        declared_personas(PersonasDeclared(own=[PersonaDeclaration(name="Not A Name", goal="g", style="s")]))


def test_a_persona_on_a_vendor_the_box_lacks_or_nobody_keyed_is_refused_at_configure() -> None:
    """What a PUT refuses of a caller's model and voice is refused when the class declares the caller."""
    lacking = PersonaDeclaration(name="on-nothing", goal="g", style="s", tts="nonvendor")
    with pytest.raises(ValidationError, match="no vendor named 'nonvendor'"):
        check_declared_personas(configured(), Keyring(), PersonasDeclared(own=[lacking]))
    unkeyed = PersonaDeclaration(name="unkeyed", goal="g", style="s", llm="openai/gpt-5.4-mini")
    with pytest.raises(ServiceUnavailable, match="openai has no key: the org brought none and the box holds none"):
        check_declared_personas(configured(), Keyring(), PersonasDeclared(own=[unkeyed]))
    check_declared_personas(configured(), Keyring(), PersonasDeclared(own=[IN_A_RUSH]))


@needs_the_database
async def test_a_judge_the_org_wrote_under_the_name_is_refused_as_the_orgs(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """One name is one question per call: the org's judge under it stands, and the class's is refused."""
    spec = spec_of("offers-next-slot", JudgeRequest(question="Did it offer a slot?"))
    async with sessions.begin() as session:
        await put_judge(session, tenant.org, THE_ORGS_OWN, spec, by="m_ana")
    config = AgentConfig(slug=AGENT, judges=JudgesDeclared(own=[OFFERS]))
    async with sessions.begin() as session:
        with pytest.raises(Conflict, match="offers-next-slot is the org's judge already"):
            await check_declared(session, configured(), Keyring(), tenant.org, AGENT, config)
        free = OFFERS.model_copy(update={"name": "offers-a-slot"})
        other = AgentConfig(slug=AGENT, judges=JudgesDeclared(own=[free]), personas=PersonasDeclared(own=[IN_A_RUSH]))
        await check_declared(session, configured(), Keyring(), tenant.org, AGENT, other)
