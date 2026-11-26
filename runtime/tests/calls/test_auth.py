"""Who reads a call, and by which declaration: the one the call opened with, whoever holds its agent now."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime import builders
from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.agents.settings import Versions
from runtime.calls.context import CallContext, Route, Visitor, dump_context, new_call_id, read_context
from runtime.calls.log.store import Store
from runtime.calls.repository.facts import FactsRepository
from runtime.calls.repository.heads import Claim
from runtime.calls.service.openings import keep_opening, opening_of
from runtime.config import load_settings
from runtime.enums import Channel, Direction, Env
from runtime.live.service.tokens import sign_log_token
from runtime.wire.events import StateChanged
from runtime.wire.worker import CallOpened
from tests.calls.factories import claim_call, logs_on
from tests.conftest import Gateway, Tenant, needs_the_services


# A page reads its call after the app that served it left: nobody holds the agent, so the call's own
# declaration is the only one that says which fields are public.
@needs_the_services
async def test_a_page_reads_the_public_fields_its_call_declared_after_the_app_left(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession], store: Store
) -> None:
    call = new_call_id()
    route = Route(org=tenant.org, agent=agent, channel=Channel.web, env=Env.sandbox)
    context = CallContext(
        call=call, channel=Channel.web, direction=Direction.inbound, caller="web_1", route=route, today=date.today()
    )
    declared = Declaration(slug=agent, state_fields={"slots": "public", "note": "tenant"})
    await claim_call(store, call, agent, Claim(Scope(tenant.org, Env.sandbox), Versions(settings=1)))
    async with sessions.begin() as session:
        await keep_opening(session, tenant.org, context, declared)
    changed = StateChanged(state={"slots": ["09:00"], "note": "pays cash"}, changed=["slots", "note"])
    # Written by another gateway of the same box: the one served reads it off the store.
    await logs_on(store).logs.writing(call, agent).append("state.changed", changed.dump())

    page = sign_log_token(builders.build_signer(load_settings()), call, "public")
    read = await gateway.http.get(
        f"/v1/calls/{call}/events", params={"token": page}, headers={"accept": "application/json"}
    )
    assert read.status_code == 200, read.text
    [state] = [entry["data"] for entry in read.json()["entries"] if entry["type"] == "state.changed"]
    assert state == {"state": {"slots": ["09:00"]}, "changed": ["slots"]}


# What the gateway saw of a web visitor's browser reaches the call when its worker opens it, and is kept
# beside its facts: the opening holds it for a call taken up later, and a list's row says it when asked.
@needs_the_services
async def test_an_opening_keeps_where_its_visitor_was_beside_the_calls_facts(
    tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    call, seen = new_call_id(), Visitor(ip="181.47.10.5", user_agent="Mozilla/5.0 Firefox/140.0", country="AR")
    route = Route(org=tenant.org, agent=agent, channel=Channel.web, env=Env.sandbox)
    today = date.today()
    context = CallContext(call, Channel.web, Direction.inbound, "web_0123456789ab", route, today, visitor=seen)
    async with sessions.begin() as session:
        await keep_opening(session, tenant.org, context, Declaration(slug=agent))
    async with sessions() as session:
        kept = await FactsRepository(session).find(call)
        opened = await opening_of(session, call)
    assert kept is not None and kept.visitor == {
        "ip": "181.47.10.5",
        "user_agent": "Mozilla/5.0 Firefox/140.0",
        "country": "AR",
    }
    assert opened is not None and opened.context.visitor == seen
    # As a worker says it: the wire's own model carries the visitor, so it is not lost between the two.
    said = CallOpened.model_validate(dump_context(context))
    assert read_context(said.model_dump(mode="json")).visitor == seen
