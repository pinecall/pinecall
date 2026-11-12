"""What a person's settings do around a Studio agent: on their written call, and on a deploy that shares them."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.calls.repository.heads import HeadRepository
from runtime.enums import Env
from runtime.kit.crypto import Vault
from runtime.kit.text import JsonObject
from runtime.providers.service import credentials
from tests.conftest import Gateway, Tenant, needs_the_services, received
from tests.fakes import acme
from tests.studio.factories import made

pytestmark = needs_the_services

PRODUCTION = {"pinecall-env": "production"}

VAULT = Vault(os.environ["PINECALL_VAULT_KEY"])


def door(agent: str) -> str:
    """The agent's settings endpoint."""
    return f"/v1/agents/{agent}/settings"


async def put_settings(gateway: Gateway, agent: str, headers: dict[str, str], body: JsonObject) -> None:
    """One PUT of the settings endpoint; it answers 200."""
    answered = await gateway.http.put(door(agent), json=body, headers=headers)
    assert answered.status_code == 200, answered.text


async def put_lexicon(gateway: Gateway, agent: str, headers: dict[str, str], body: JsonObject) -> None:
    """One PUT of the lexicon endpoint; it answers 200."""
    answered = await gateway.http.put(f"/v1/agents/{agent}/lexicon", json=body, headers=headers)
    assert answered.status_code == 200, answered.text


async def history(gateway: Gateway, agent: str, headers: dict[str, str], **query: str) -> list[JsonObject]:
    """The agent's settings versions in that scope, newest first."""
    answered = await gateway.http.get(f"{door(agent)}/history", params=query, headers=headers)
    assert answered.status_code == 200, answered.text
    return list(answered.json()["rows"])


async def deploy(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """The newest release deployed by the tenant's admin; it answers 200."""
    answered = await gateway.http.post(f"/v1/studio/agents/{agent}/deploy", json={}, headers=tenant.person)
    assert answered.status_code == 200, answered.text


async def deployable(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """The clinic made in Studio and held, with its secret set in production, which a deploy checks."""
    await made(gateway, tenant, agent)
    secret = await gateway.http.put(
        "/v1/secrets/AGENDA_KEY", json={"value": "the-key"}, headers={**tenant.person, **PRODUCTION}
    )
    assert secret.status_code < 300, secret.text


# ── a person's written call ──


async def test_a_persons_written_call_runs_on_their_settings_and_a_server_keys_stays_the_orgs(
    sessions: async_sessionmaker[AsyncSession], gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The person's second version tunes their call, in their scope; a server key's call is the team's."""
    await made(gateway, tenant, agent)
    await put_settings(gateway, agent, tenant.person, {"config": {"language": "fr-FR"}, "team": True})
    await put_settings(gateway, agent, tenant.person, {"config": {"language": "de-DE"}})
    await put_settings(gateway, agent, tenant.person, {"config": {"language": "es-ES"}})
    async with gateway.socket(f"/v1/chat?agent={agent}", tenant.person) as chat:
        theirs = str((await received(chat, "call.started"))["call"])
    async with gateway.socket(f"/v1/chat?agent={agent}", tenant.server) as chat:
        the_orgs = str((await received(chat, "call.started"))["call"])
    async with sessions() as session:
        heads = HeadRepository(session)
        person, server = await heads.head_of_call(theirs), await heads.head_of_call(the_orgs)
    assert person is not None and person.scope == Scope(tenant.org, Env.sandbox, tenant.member)
    assert person.versions.settings == 2
    assert server is not None and server.scope == Scope(tenant.org, Env.sandbox)
    assert server.versions.settings == 1


# ── a deploy ──


async def test_a_deploy_carries_the_deployers_settings_and_keeps_what_the_sandbox_leaves_unset(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """Each corner takes what the sandbox set; what production alone had stays, the note and author say who."""
    production = {**tenant.person, **PRODUCTION}
    await deployable(gateway, tenant, agent)
    await put_settings(gateway, agent, production, {"config": {"language": "de-DE", "record": False}})
    await put_lexicon(
        gateway, agent, production, {"lexicon": {"said": [{"word": "Dr", "spoken": "Doctor"}], "heard": ["norte"]}}
    )
    await put_settings(gateway, agent, tenant.person, {"config": {"max_duration_s": 600}, "team": True})
    await put_settings(gateway, agent, tenant.person, {"config": {"language": "es-ES", "temperature": 0.5}})
    await put_lexicon(
        gateway, agent, tenant.person, {"lexicon": {"said": [{"word": "cita", "spoken": "turno"}], "heard": []}}
    )
    before = await gateway.http.get(door(agent), headers=production)
    await deploy(gateway, tenant, agent)
    after = await gateway.http.get(door(agent), headers=production)
    newest = after.json()["production"]
    assert newest["config"] == {"language": "es-ES", "record": False, "max_duration_s": 600, "temperature": 0.5}
    assert newest["version"] == before.json()["production"]["version"] + 1
    assert newest["note"] == "deployed from the sandbox's release 1"
    assert newest["author"] == "The admin"
    team = await gateway.http.get(door(agent), headers=tenant.person)
    assert team.json()["team"]["config"] == {"language": "es-ES", "max_duration_s": 600, "temperature": 0.5}
    # The person's own corner is theirs: a deploy reads it and leaves it.
    assert team.json()["yours"]["config"] == {"language": "es-ES", "temperature": 0.5}
    words = await gateway.http.get(f"/v1/agents/{agent}/lexicon", headers=production)
    said = {item["word"]: item["spoken"] for item in words.json()["production"]["lexicon"]["said"]}
    assert said == {"Dr": "Doctor", "cita": "turno"}
    assert words.json()["production"]["lexicon"]["heard"] == ["norte"]


async def test_a_sandbox_with_no_settings_writes_no_version_and_a_second_deploy_writes_none_again(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """An empty sandbox clears nothing; deployed unchanged, production and the team keep their one version."""
    production = {**tenant.person, **PRODUCTION}
    await deployable(gateway, tenant, agent)
    await deploy(gateway, tenant, agent)
    assert await history(gateway, agent, production) == []
    assert await history(gateway, agent, tenant.person, team="true") == []
    await put_settings(gateway, agent, tenant.person, {"config": {"record": False}})
    await deploy(gateway, tenant, agent)
    await deploy(gateway, tenant, agent)
    assert len(await history(gateway, agent, production)) == 1
    assert len(await history(gateway, agent, tenant.person, team="true")) == 1


async def test_a_vendor_refusing_what_a_deploy_carries_leaves_no_release_and_no_settings(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Refused by the vendor, the deploy lands in one piece or not at all: no release, no version."""
    production = {**tenant.person, **PRODUCTION}
    await deployable(gateway, tenant, agent)
    await put_settings(gateway, agent, tenant.person, {"config": {"temperature": 0.5}})
    # The org's key, taken when it was brought, has been revoked at the vendor since.
    async with sessions.begin() as session:
        revoked = credentials.read_credentials(acme.A_REFUSED_KEY, None)
        await credentials.put_own_credentials(session, VAULT, tenant.org, acme.ACME, revoked)
    answered = await gateway.http.post(f"/v1/studio/agents/{agent}/deploy", json={}, headers=tenant.person)
    assert answered.status_code == 400, answered.text
    assert f"{acme.ACME} refused" in answered.json()["detail"]
    there = await gateway.http.get(f"/v1/studio/agents/{agent}", headers=production)
    assert there.status_code == 404
    assert await history(gateway, agent, production) == []
    assert await history(gateway, agent, tenant.person, team="true") == []
