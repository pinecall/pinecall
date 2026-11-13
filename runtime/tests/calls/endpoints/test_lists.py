"""The calls lists: in the sandbox, the reader's own copy and the org's, every copy to a key that opens colleagues'."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service import invitations, keys
from runtime.accounts.service.key_cache import KeyCache
from runtime.actor import THE_ORGS_OWN, Scope
from runtime.agents.settings import Versions
from runtime.calls.context import new_call_id
from runtime.calls.log.store import Store
from runtime.calls.repository.heads import Claim
from runtime.calls.service import simulated
from runtime.enums import Env, Role
from tests.calls.factories import a_call_with_tools, claim_call, logs_on
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


async def a_developer(sessions: async_sessionmaker[AsyncSession], cache: KeyCache, tenant: Tenant) -> Colleague:
    """A developer seated in the tenant's org, and their key."""
    async with sessions.begin() as session:
        invitee = invitations.Invitee(f"dev@{tenant.slug}.test", "Dana Dev", Role.developer)
        invited = await invitations.invite(session, tenant.org, invitee, vouched=True, held_to_seats=False)
    async with sessions.begin() as session:
        seated = await invitations.accept_link(session, cache, invited.token, "a-password-for-dana", 8)
        assert seated is not None
        issued = await keys.issue_person_key(session, seated.member)
    return Colleague(seated.id, issued.secret)


# Written by another gateway of the same box: the one served lists and reads it off the store.
async def a_call_on(store: Store, tenant: Tenant, agent: str, holder: str) -> str:
    """A call the agent took on that copy in the sandbox, written from its start to its last tool."""
    call = new_call_id()
    await claim_call(store, call, agent, Claim(Scope(tenant.org, Env.sandbox, holder), Versions(settings=1)))
    writing = logs_on(store).logs.writing(call, agent)
    for written in a_call_with_tools(call, agent):
        await writing.append(written.type, written.data)
    return call


async def listed(gateway: Gateway, headers: dict[str, str], **query: Any) -> list[dict[str, Any]]:
    """The org's calls as these headers list them."""
    answer = await gateway.http.get("/v1/sessions", params=query, headers=headers)
    assert answer.status_code == 200, answer.text
    return list(answer.json()["calls"])


async def test_a_developer_lists_their_copy_and_the_orgs_and_an_admin_lists_every_copy_named(
    gateway: Gateway,
    tenant: Tenant,
    agent: str,
    sessions: async_sessionmaker[AsyncSession],
    store: Store,
    key_cache: KeyCache,
) -> None:
    dana = await a_developer(sessions, key_cache, tenant)
    orgs = await a_call_on(store, tenant, agent, THE_ORGS_OWN)
    admins = await a_call_on(store, tenant, agent, tenant.member)
    danas = await a_call_on(store, tenant, agent, dana.id)

    assert {row["call"] for row in await listed(gateway, dana.headers)} == {orgs, danas}
    every = await listed(gateway, tenant.person, holders="true")
    assert {row["call"]: (row["holder"], row["holder_name"]) for row in every} == {
        orgs: ("", None),
        admins: (tenant.member, "The admin"),
        danas: (dana.id, "Dana Dev"),
    }
    # A list not asked for whose copy is the row an app built before strict-parses.
    assert all("holder" not in row and "holder_name" not in row for row in await listed(gateway, tenant.person))


# A golden's call is opened like a visitor's: the row says whose run it is to a reader who asks.
async def test_a_runs_call_says_its_run_to_a_list_asked_with_runs(
    gateway: Gateway, tenant: Tenant, agent: str, store: Store
) -> None:
    a_persons = await a_call_on(store, tenant, agent, tenant.member)
    a_goldens = new_call_id()
    claimed = Claim(Scope(tenant.org, Env.sandbox, tenant.member), Versions(settings=1), run="run_1")
    await claim_call(store, a_goldens, agent, claimed)
    writing = logs_on(store).logs.writing(a_goldens, agent)
    for written in a_call_with_tools(a_goldens, agent):
        await writing.append(written.type, written.data)

    every = await listed(gateway, tenant.person, runs="true")
    assert {row["call"]: row["run"] for row in every} == {a_persons: None, a_goldens: "run_1"}
    # A list not asked for it is the row an app built before strict-parses.
    assert all("run" not in row for row in await listed(gateway, tenant.person))


async def test_an_admin_opens_a_colleagues_call_and_a_developer_does_not(
    gateway: Gateway,
    tenant: Tenant,
    agent: str,
    sessions: async_sessionmaker[AsyncSession],
    store: Store,
    key_cache: KeyCache,
) -> None:
    dana = await a_developer(sessions, key_cache, tenant)
    admins = await a_call_on(store, tenant, agent, tenant.member)
    danas = await a_call_on(store, tenant, agent, dana.id)

    def events(call: str) -> str:
        return f"/v1/calls/{call}/events"

    as_json = {"accept": "application/json"}
    read = await gateway.http.get(events(danas), headers={**tenant.person, **as_json})
    assert read.status_code == 200, read.text
    refused = await gateway.http.get(events(admins), headers={**dana.headers, **as_json})
    assert refused.status_code == 404, refused.text


# A Studio agent is the org's own copy: a simulation against it is listed and its comparison read
# by the person who placed it, whose own copy holds nothing of it.
async def test_a_simulation_the_orgs_own_copy_took_is_listed_and_its_comparison_read(
    gateway: Gateway,
    tenant: Tenant,
    agent: str,
    sessions: async_sessionmaker[AsyncSession],
    store: Store,
    key_cache: KeyCache,
) -> None:
    call = await a_call_on(store, tenant, agent, THE_ORGS_OWN)
    comparison = f"cmp_{call[-6:]}"
    async with sessions.begin() as session:
        await simulated.keep_agent_values(session, call, against={}, comparison=comparison, persona="in-a-hurry")

    runs = await gateway.http.get("/v1/simulations", params={"comparison": comparison}, headers=tenant.person)
    assert runs.status_code == 200, runs.text
    assert [run["call"] for run in runs.json()["runs"]] == [call]
    table = await gateway.http.get(f"/v1/simulations/compare/{comparison}", headers=tenant.person)
    assert table.status_code == 200, table.text
    assert (table.json()["personas"], [row["call"] for row in table.json()["rows"]]) == (["in-a-hurry"], [call])
