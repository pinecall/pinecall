"""Who reads a call, and by which declaration: the one the call opened with, whoever holds its agent now."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime import builders
from runtime.actor import Scope
from runtime.agents.declaration import Declaration
from runtime.agents.settings import Versions
from runtime.calls.context import CallContext, Route, new_call_id
from runtime.calls.log.store import Store
from runtime.calls.repository.heads import Claim
from runtime.calls.service.openings import keep_opening
from runtime.config import load_settings
from runtime.enums import Channel, Direction, Env
from runtime.live.service.tokens import sign_log_token
from runtime.wire.events import StateChanged
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
