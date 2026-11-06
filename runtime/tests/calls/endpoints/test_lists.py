"""The calls lists: in the sandbox, the reader's own copy and the org's, every copy to a key that opens colleagues'."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import keys, members
from pinecall_runtime.agents.declaration import Versions
from pinecall_runtime.calls.context import new_call_id
from pinecall_runtime.calls.repository.heads import Claim
from pinecall_runtime.enums import Env, Role
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Scope
from tests.calls.factories import a_call_with_tools
from tests.conftest import Gateway, Tenant, needs_the_services

pytestmark = needs_the_services


@dataclass(frozen=True)
class Colleague:
    """A developer of the tenant's org, with the key they work with."""

    id: str
    key: str

    @property
    def headers(self) -> dict[str, str]:
        """Their headers, in the sandbox."""
        return {"authorization": f"Bearer {self.key}", "pinecall-env": Env.sandbox.value}


async def a_developer(sessions: async_sessionmaker[AsyncSession], tenant: Tenant) -> Colleague:
    """A developer seated in the tenant's org, and their key."""
    async with sessions.begin() as session:
        invitee = members.Invitee(f"dev@{tenant.slug}.test", "Dana Dev", Role.developer)
        invited = await members.invite(session, tenant.org, invitee, seats=None, vouched=True)
    async with sessions.begin() as session:
        seated = await members.accept_link(session, invited.token, "a-password-for-dana", 8)
        assert seated is not None
        _, secret = await keys.issue_person_key(session, seated)
    return Colleague(seated.id, secret)


async def a_call_on(gateway: Gateway, tenant: Tenant, agent: str, holder: str) -> str:
    """A call the agent took on that copy in the sandbox, written from its start to its last tool."""
    logs = gateway.app.state.serving.logs
    call = new_call_id()
    await logs.store.claim(call, agent, tenant.org, Claim(Scope(tenant.org, Env.sandbox, holder), Versions(config=1)))
    writing = logs.writing(call, agent)
    for written in a_call_with_tools(call, agent):
        await writing.append(written.type, written.data)
    return call


async def listed(gateway: Gateway, headers: dict[str, str], **query: Any) -> list[dict[str, Any]]:
    """The org's calls as these headers list them."""
    answer = await gateway.http.get("/v1/sessions", params=query, headers=headers)
    assert answer.status_code == 200, answer.text
    return list(answer.json()["calls"])


async def test_a_developer_lists_their_copy_and_the_orgs_and_an_admin_lists_every_copy_named(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    dana = await a_developer(sessions, tenant)
    orgs = await a_call_on(gateway, tenant, agent, THE_ORGS_OWN)
    admins = await a_call_on(gateway, tenant, agent, tenant.member)
    danas = await a_call_on(gateway, tenant, agent, dana.id)

    assert {row["call"] for row in await listed(gateway, dana.headers)} == {orgs, danas}
    every = await listed(gateway, tenant.person, holders="true")
    assert {row["call"]: (row["holder"], row["holder_name"]) for row in every} == {
        orgs: ("", None),
        admins: (tenant.member, "The admin"),
        danas: (dana.id, "Dana Dev"),
    }
    # A list not asked for whose copy is the row an app built before strict-parses.
    assert all("holder" not in row and "holder_name" not in row for row in await listed(gateway, tenant.person))


async def test_an_admin_opens_a_colleagues_call_and_a_developer_does_not(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    dana = await a_developer(sessions, tenant)
    admins = await a_call_on(gateway, tenant, agent, tenant.member)
    danas = await a_call_on(gateway, tenant, agent, dana.id)

    def events(call: str) -> str:
        return f"/v1/calls/{call}/events"

    as_json = {"accept": "application/json"}
    read = await gateway.http.get(events(danas), headers={**tenant.person, **as_json})
    assert read.status_code == 200, read.text
    refused = await gateway.http.get(events(admins), headers={**dana.headers, **as_json})
    assert refused.status_code == 404, refused.text
