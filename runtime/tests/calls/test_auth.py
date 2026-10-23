"""Who reads a call, and by which declaration: the one the call opened with, whoever holds its agent now."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import tokens
from pinecall_runtime.agents.declaration import AgentConfig, Versions
from pinecall_runtime.calls.context import CallContext, Route, new_call_id
from pinecall_runtime.calls.repository.heads import Claim
from pinecall_runtime.calls.service.openings import keep_opening
from pinecall_runtime.enums import Channel, Direction, Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.events import StateChanged
from tests.conftest import Gateway, Tenant, needs_the_services


# A page reads its call after the app that served it left: nobody holds the agent, so the call's own
# declaration is the only one that says which fields are public.
@needs_the_services
async def test_a_page_reads_the_public_fields_its_call_declared_after_the_app_left(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    serving = gateway.app.state.serving
    call = new_call_id()
    route = Route(org=tenant.org, agent=agent, channel=Channel.web, env=Env.sandbox)
    context = CallContext(
        call=call, channel=Channel.web, direction=Direction.inbound, caller="web_1", route=route, today=date.today()
    )
    declared = AgentConfig(slug=agent, state_fields={"slots": "public", "note": "tenant"})
    await serving.logs.store.claim(call, agent, tenant.org, Claim(Scope(tenant.org, Env.sandbox), Versions(config=1)))
    async with sessions.begin() as session:
        await keep_opening(session, tenant.org, context, declared)
    changed = StateChanged(state={"slots": ["09:00"], "note": "pays cash"}, changed=["slots", "note"])
    await serving.logs.writing(call, agent).append("state.changed", changed.dump())

    page = tokens.log_token(serving.signer, call, "public")
    read = await gateway.http.get(
        f"/v1/calls/{call}/events", params={"token": page}, headers={"accept": "application/json"}
    )
    assert read.status_code == 200, read.text
    [state] = [entry["data"] for entry in read.json()["entries"] if entry["type"] == "state.changed"]
    assert state == {"state": {"slots": ["09:00"]}, "changed": ["slots"]}
