"""Studio's doors on the served gateway: an agent made, saved over the release read, tried, deployed, exported."""

import io
import zipfile

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.calls.log.store import Store
from tests.calls.factories import claim_agent_log
from tests.conftest import Gateway, Tenant, make_tenant, needs_the_services
from tests.studio.factories import clinic

pytestmark = needs_the_services

PRODUCTION = {"pinecall-env": "production"}


def body(name: str, **changes: object) -> dict[str, object]:
    """A new agent's body: the clinic, its secret-free variant unless asked."""
    definition = clinic(tools=[], **changes).model_dump(mode="json", exclude_none=True)
    return {"name": name, "definition": definition}


async def test_an_agent_is_made_read_and_saved_over_the_release_it_was_read_at(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """Made at release 1; a save over 1 is 2; a second save over 1 is told someone saved meanwhile."""
    made = await gateway.http.post("/v1/studio/agents", json=body(agent), headers=tenant.person)
    assert made.status_code == 200, made.text
    assert made.json()["release"] == 1
    read = await gateway.http.get(f"/v1/studio/agents/{agent}", headers=tenant.person)
    assert read.json()["definition"]["instructions"].startswith("You answer the phone for Clínica Norte")
    changed = {**read.json()["definition"], "instructions": "You answer for the clinic, briefly."}
    saved = await gateway.http.put(
        f"/v1/studio/agents/{agent}", json={"definition": changed, "based_on": 1}, headers=tenant.person
    )
    assert saved.status_code == 200 and saved.json()["release"] == 2
    stale = await gateway.http.put(
        f"/v1/studio/agents/{agent}", json={"definition": changed, "based_on": 1}, headers=tenant.person
    )
    assert stale.status_code == 409 and "release 2" in stale.json()["detail"]
    listed = await gateway.http.get("/v1/studio/agents", headers=tenant.person)
    assert [item["name"] for item in listed.json()["agents"]] == [agent]


async def test_a_name_another_orgs_agent_has_is_refused_and_nothing_is_kept(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession], store: Store
) -> None:
    """A slug is one org's: made all the same, the holder could never register it, and it would answer nothing."""
    theirs = await make_tenant(sessions)
    await claim_agent_log(store, agent, theirs.org)
    refused = await gateway.http.post("/v1/studio/agents", json=body(agent), headers=tenant.person)
    assert refused.status_code == 409 and "another organization's agent" in refused.json()["detail"]
    apps = (await gateway.http.get("/v1/hosted", headers=tenant.person)).json()["apps"]
    assert agent not in [app["name"] for app in apps], "the refusal kept a hosted app"
    made = await gateway.http.post("/v1/studio/agents", json=body(agent), headers=theirs.person)
    assert made.status_code == 200, "the org the name belongs to makes it"


async def test_a_studio_agent_is_a_hosted_app_of_the_studio_kind(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """The Apps list shows it, held as its newest release; sources uploaded under its name are refused."""
    await gateway.http.post("/v1/studio/agents", json=body(agent), headers=tenant.person)
    apps = (await gateway.http.get("/v1/hosted", headers=tenant.person)).json()["apps"]
    row = next(app for app in apps if app["name"] == agent)
    assert row["kind"] == "studio" and row["live_release"] == 1
    upload = await gateway.http.post(
        f"/v1/hosted/{agent}/releases", content=b"x", headers={**tenant.server, "content-type": "application/gzip"}
    )
    assert upload.status_code == 400 and "Studio agent" in upload.json()["detail"]


async def test_a_definition_naming_a_secret_the_env_lacks_is_refused_until_it_is_set(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The secret is said by name; once set in the env the same definition is taken."""
    with_secret = {"name": agent, "definition": clinic().model_dump(mode="json", exclude_none=True)}
    refused = await gateway.http.post("/v1/studio/agents", json=with_secret, headers=tenant.person)
    assert refused.status_code == 400 and "AGENDA_KEY" in refused.json()["detail"]
    await gateway.http.put("/v1/secrets/AGENDA_KEY", json={"value": "k"}, headers=tenant.person)
    made = await gateway.http.post("/v1/studio/agents", json=with_secret, headers=tenant.person)
    assert made.status_code == 200, made.text


async def test_a_deploy_lands_the_sandbox_release_in_production_for_a_person_who_may_act_there(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """A server's key may not deploy; the admin may, and production holds release 1 with the same definition."""
    await gateway.http.post("/v1/studio/agents", json=body(agent), headers=tenant.person)
    by_a_server = await gateway.http.post(f"/v1/studio/agents/{agent}/deploy", json={}, headers=tenant.server)
    assert by_a_server.status_code == 403
    deployed = await gateway.http.post(f"/v1/studio/agents/{agent}/deploy", json={}, headers=tenant.person)
    assert deployed.status_code == 200, deployed.text
    assert deployed.json()["env"] == "production" and deployed.json()["release"] == 1
    there = await gateway.http.get(f"/v1/studio/agents/{agent}", headers={**tenant.person, **PRODUCTION})
    assert there.json()["definition"] == deployed.json()["definition"]


async def test_try_sends_one_tools_request_with_the_envs_secret(
    gateway: Gateway, tenant: Tenant, agent: str, agenda: list[httpx.Request]
) -> None:
    """The editor's Try: the unsaved definition's tool, the path filled, the header's secret opened."""
    await gateway.http.put("/v1/secrets/AGENDA_KEY", json={"value": "the-key"}, headers=tenant.person)
    await gateway.http.post("/v1/studio/agents", json=body(agent), headers=tenant.person)
    tried = await gateway.http.post(
        f"/v1/studio/agents/{agent}/try",
        json={
            "tool": "findPatient",
            "arguments": {"phone": "+59899123456"},
            "definition": clinic().model_dump(mode="json", exclude_none=True),
        },
        headers=tenant.person,
    )
    assert tried.status_code == 200, tried.text
    assert tried.json()["status"] == 200 and tried.json()["body"]["patient"]["name"] == "Ana Ruiz"
    assert str(agenda[-1].url) == "https://agenda.example.com/patients/%2B59899123456"
    assert agenda[-1].headers["authorization"] == "Bearer the-key"


async def test_the_code_door_answers_the_agent_as_a_project_zipped(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """Download code: the class of its newest release, ready for `pinecall deploy`."""
    await gateway.http.post("/v1/studio/agents", json=body(agent), headers=tenant.person)
    answered = await gateway.http.get(f"/v1/studio/agents/{agent}/code", headers=tenant.person)
    assert answered.status_code == 200 and answered.headers["content-type"] == "application/zip"
    zipped = zipfile.ZipFile(io.BytesIO(answered.content))
    assert f"{agent}/agents/{agent}/agent.tsx" in zipped.namelist()
