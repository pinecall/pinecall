"""A written call: taken up again on the context it opened with, and a golden's recall answered with its facts."""

from dataclasses import replace
from datetime import date

from runtime.actor import Scope
from runtime.agents.declaration import Declaration, Docs, MemoryPolicy
from runtime.agents.service.kinds import BUILT_IN_STUDIO
from runtime.calls.context import Contact
from runtime.enums import Channel, Env
from runtime.live.holders import Registration
from runtime.live.parts import LiveParts
from runtime.live.served import Opening
from runtime.live.service import openings
from runtime.live.service.written import A_GOLDEN, GatewayPlatform, context_as_started, registration_for
from tests.calls.factories import AGENT, CALL, CALLER, LINE, entry
from tests.conftest import needs_the_database
from tests.session.conftest import context_of

SCOPE = Scope("org_1", Env.sandbox)
THEIR_SCOPE = Scope("org_1", Env.sandbox, "mem_1")
REGISTRATION = Registration(slug=AGENT, scope=SCOPE, owner="socket_1")
TODAY = date(2026, 10, 23)


def taken_up(caller: object) -> Contact | None:
    """The contact a call is rebuilt with, from a call.started that names this caller."""
    line = {**LINE, "channel": "web", "direction": "inbound", "caller": caller, "started_at": 1_790_000_000.0}
    return context_as_started(CALL, AGENT, SCOPE, [entry(1, "call.started", line)], TODAY).contact


def test_a_call_taken_up_again_keeps_the_contact_it_opened_with_so_memory_files_what_it_teaches_there() -> None:
    """`chat --as`: after the gateway that held the call restarts, the next one still knows who is calling."""
    assert taken_up({"id": "ct_9", "name": "Marta"}) == Contact(id="ct_9", name="Marta")
    assert taken_up(CALLER) == Contact(id="ct_9", phone="+34611222333", name="Marta")


def test_a_call_opened_with_nobody_named_is_taken_up_with_nobody() -> None:
    """No caller on the entry, no contact on the context: the visitor id stays the only thing it knows."""
    assert taken_up(None) is None


def test_a_persons_written_call_to_a_studio_agent_is_claimed_in_their_scope_on_the_orgs_socket() -> None:
    """The socket stays the org's; the scope is the person's, as their voice call's is."""
    studio = replace(REGISTRATION, sdk=BUILT_IN_STUDIO)
    theirs = registration_for(studio, THEIR_SCOPE)
    assert theirs.scope == THEIR_SCOPE and theirs.owner == studio.owner


def test_a_class_keeps_the_scope_it_is_held_in_and_nobodys_key_changes_a_studio_agent() -> None:
    """An app written as a class is untouched; a server's key and production name no holder."""
    assert registration_for(REGISTRATION, THEIR_SCOPE) is REGISTRATION
    assert registration_for(replace(REGISTRATION, sdk=BUILT_IN_STUDIO), SCOPE).scope == SCOPE


# ── a golden's recall ──

A_FACT = "Ana prefiere los martes por la mañana"


def golden_call(live: LiveParts, call: str, declaration: Declaration) -> GatewayPlatform:
    """A written call of a golden that seeds one fact, as the gateway serves it."""
    opening = Opening(context_of(call, Channel.web), declaration, SCOPE, None)
    served = openings.serve(live, opening, opened_here=True)
    return GatewayPlatform(live, served, (A_FACT,))


@needs_the_database
async def test_a_goldens_recall_is_its_own_facts_written_as_a_real_one_so_the_app_learns_them(
    live: LiveParts, call: str
) -> None:
    platform = golden_call(live, call, Declaration(slug=AGENT, memory=MemoryPolicy()))
    found = await platform.look_up("recall", {"query": "martes"}, "s1")
    assert found == {"facts": [{"text": A_FACT, "source": A_GOLDEN}]}
    (written,) = [entry for entry in await live.store.whole_of(call) if entry.type == "memory.ops"]
    facts = [{"text": A_FACT, "source": A_GOLDEN}]
    assert written.data["ops"] == [{"op": "recall", "query": "martes", "facts": facts, "took_ms": 0.0}]
    assert written.data["speech_id"] == "s1"
    live.calls.close_call(call)


# A golden asks what the index finds: its search is the real one, never its seeded facts.
@needs_the_database
async def test_a_goldens_search_is_the_real_index(live: LiveParts, call: str) -> None:
    platform = golden_call(live, call, Declaration(slug=AGENT, bases=(Docs(base="precios"),)))
    found = await platform.look_up("search", {"query": "precio"}, None)
    assert "facts" not in found and A_FACT not in str(found)
    live.calls.close_call(call)
