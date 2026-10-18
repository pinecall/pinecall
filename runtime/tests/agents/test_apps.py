"""An agent killed: every app that holds it lets go of it and keeps its others; an admin's, or the operator's."""

import json

from websockets.asyncio.client import ClientConnection

from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.service.kills import sockets_holding
from pinecall_runtime.calls.service.peers import tell_app
from pinecall_runtime.enums import Env
from pinecall_runtime.wire.commands import AgentRegister
from pinecall_runtime.wire.signal import ForApp, Killed
from tests.conftest import BOX, Gateway, Tenant, holding, needs_the_services, received

KILLED = "killed"


async def also_holds(app: ClientConnection, agent: str) -> None:
    """The socket declares a second agent, as an app that holds a whole project does."""
    register = AgentRegister(routes=[]).model_dump(mode="json")
    await app.send(json.dumps({"type": "agent.register", "agent": agent, "call": None, "data": register}))
    await received(app, "agent.registered")


async def held(gateway: Gateway, tenant: Tenant) -> list[str]:
    """The slugs the org's agents list shows, as the console and the playground read them."""
    answer = await gateway.http.get("/v1/agents", headers=tenant.server)
    return sorted(row["slug"] for row in answer.json()["agents"])


async def still_answers(app: ClientConnection, agent: str) -> None:
    """The socket is open and the agent still its own: a ping for it is answered."""
    await app.send(json.dumps({"type": "ping", "agent": agent, "call": None, "data": {}}))
    assert (await received(app, "pong"))["agent"] == agent


@needs_the_services
async def test_an_admin_kills_one_agent_and_the_app_keeps_the_other(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    other = f"{agent}-other"
    async with holding(gateway, tenant, agent) as app:
        await also_holds(app, other)
        answer = await gateway.http.post(f"/v1/agents/{agent}/kill", headers=tenant.person)
        assert answer.status_code == 200, answer.text
        assert (answer.json()["agent"], answer.json()["envs"], len(answer.json()["apps"])) == (agent, ["sandbox"], 1)
        told = await received(app, "error")
        assert (told["agent"], told["data"]["code"], told["data"]["recoverable"]) == (agent, KILLED, False)
        assert "was killed by" in told["data"]["message"]
        assert await held(gateway, tenant) == [other]
        await still_answers(app, other)


@needs_the_services
async def test_a_key_that_is_not_an_admins_kills_nothing_and_an_agent_nobody_holds_is_404(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent):
        refused = await gateway.http.post(f"/v1/agents/{agent}/kill", headers=tenant.server)
        assert refused.status_code == 403, refused.text
        assert "an admin's" in refused.json()["detail"]
        assert await held(gateway, tenant) == [agent]
    nobody = await gateway.http.post(f"/v1/agents/{agent}/kill", headers=tenant.person)
    assert nobody.status_code == 404, nobody.text
    assert "no app holds" in nobody.json()["detail"]


@needs_the_services
async def test_the_operator_kills_an_agent_of_an_org_from_the_boxs_own_key(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent) as app:
        answer = await gateway.http.post(f"/v1/ops/orgs/{tenant.slug}/agents/{agent}/kill", headers=BOX)
        assert answer.status_code == 200, answer.text
        assert answer.json()["envs"] == ["sandbox"]
        told = await received(app, "error")
        assert (told["agent"], told["data"]["code"]) == (agent, KILLED)
        assert "operator" in told["data"]["message"]
        assert await held(gateway, tenant) == []
    tenants = await gateway.http.post(f"/v1/ops/orgs/{tenant.slug}/agents/{agent}/kill", headers=tenant.person)
    assert tenants.status_code == 403, tenants.text


# Another gateway holds no socket object: it says the kill on the socket's inbox, as it says a stop.
@needs_the_services
async def test_a_kill_said_on_the_sockets_inbox_lets_go_as_one_asked_here(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    serving: calls.Serving = gateway.app.state.serving
    async with holding(gateway, tenant, agent) as app:
        (socket,) = sockets_holding(serving.registry, tenant.org, Env.sandbox, agent)
        assert await tell_app(serving.live.signal, socket, ForApp(kill=Killed(agent=agent, why="from another gateway")))
        told = await received(app, "error")
        assert (told["agent"], told["data"]["code"], told["data"]["message"]) == (agent, KILLED, "from another gateway")
        assert await held(gateway, tenant) == []
