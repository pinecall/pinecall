"""The gateway holding a Studio agent: registered on its own socket, refused to anyone else, its calls answered."""

import asyncio
import json
import time
from datetime import date
from functools import partial

import httpx

from pinecall_runtime.calls.context import CallContext, Route, new_call_id
from pinecall_runtime.calls.schemas import OpenCallRequest, SealCallRequest
from pinecall_runtime.enums import Channel, Direction, Env
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.session.writing import Writing
from pinecall_runtime.wire.base import Command
from pinecall_runtime.wire.commands import AgentRegister
from pinecall_runtime.wire.events import CallEnded, CallStarted
from tests.conftest import Gateway, Tenant, needs_the_services, received, until
from tests.studio.test_definition import clinic
from tests.studio.test_endpoints import faked_api

pytestmark = needs_the_services
__all__ = ["faked_api"]


async def made(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """The clinic made in Studio, its secret set, and held by this gateway."""
    await gateway.http.put("/v1/secrets/AGENDA_KEY", json={"value": "the-key"}, headers=tenant.person)
    definition = clinic().model_dump(mode="json", exclude_none=True)
    answered = await gateway.http.post(
        "/v1/studio/agents", json={"name": agent, "definition": definition}, headers=tenant.person
    )
    assert answered.status_code == 200, answered.text
    # Every gateway of a parallel run shares Redis, so the registry says it is held as soon as any of
    # them holds it: this gateway's own Studio socket is what the test's calls and asserts reach.
    holder = gateway.app.state.studio

    registry = gateway.app.state.registry

    def held_here() -> bool:
        socket = holder.sockets.get((tenant.org, Env.sandbox))
        return socket is not None and registry.on_socket(socket.socket.id, Env.sandbox, agent) is not None

    await until(held_here)


def a_voice_call(tenant: Tenant, agent: str) -> CallContext:
    """A sandbox call of the agent, as a worker opens it."""
    return CallContext(
        call=new_call_id(),
        channel=Channel.web,
        direction=Direction.inbound,
        caller="+59899123456",
        route=Route(org=tenant.org, agent=agent, channel=Channel.web, env=Env.sandbox),
        today=date(2026, 10, 19),
    )


async def test_a_studio_agent_is_held_by_the_gateway_and_listed_as_its_process(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """Made in Studio, it is held at once, by the process the console names Pinecall Studio."""
    await made(gateway, tenant, agent)
    processes = (await gateway.http.get("/v1/apps", headers=tenant.person)).json()
    assert any(agent in json.dumps(item) and "pinecall-studio" in json.dumps(item) for item in processes["apps"])


async def test_an_app_registering_a_studio_agents_slug_is_refused(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """A slug is one agent: a terminal's `pinecall start` of the same name is told it is Studio's."""
    await made(gateway, tenant, agent)
    async with gateway.socket("/v1/apps", tenant.server) as app:
        register = AgentRegister(routes=[]).model_dump(mode="json")
        await app.send(json.dumps({"type": "agent.register", "agent": agent, "call": None, "data": register}))
        refused = await received(app, "error")
    assert "Studio agent" in refused["data"]["message"]


async def test_a_call_is_answered_from_the_definition_its_tools_run_and_its_results_posted(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient, faked_api: list[httpx.Request]
) -> None:
    """The prompt rendered for the caller, the lookup sent, collect saving the name, the fields posted at the end."""
    await made(gateway, tenant, agent)
    context = a_voice_call(tenant, agent)
    # Every gateway of the run shares Redis and so holds the agent too: the call is bound to this
    # gateway's Studio socket, the one whose requests the fake agenda answers.
    ours = gateway.app.state.studio.sockets[(tenant.org, Env.sandbox)].socket.id
    await fleet.open(OpenCallRequest(agent=agent, context=context, app=ours))
    commands: list[Command] = []

    async def follow() -> None:
        async for command in fleet.commands(context.call):
            commands.append(command)

    following = asyncio.create_task(follow())
    writing = Writing(partial(fleet.append_many, context.call), context.call)
    writing.open()
    started = CallStarted.model_validate(
        {
            "channel": "web",
            "direction": "inbound",
            "from": "+59899123456",
            "to": agent,
            "caller": None,
            "started_at": time.time(),
        }
    )
    await writing.write("call.started", started)

    def prompt(name: str) -> str | None:
        sent = [c.data["text"] for c in commands if c.type == "prompt.set" and c.data["name"] == name]
        return sent[-1] if sent else None

    # The blocks go out in order, identity, tools, view: the last one landed is all of them.
    await until(lambda: prompt("view") is not None)
    identity = prompt("identity") or ""
    assert identity.startswith("You answer the phone for Clínica Norte. The caller dials from +59899123456.")
    assert "<protocols>" in identity
    assert (prompt("tools") or "").startswith("<tools>\n- findPatient: Finds the patient by phone.")
    assert "Still to collect" in (prompt("view") or "")

    looked_up = await fleet.tool(
        context.call, agent, {"call_id": "c1", "name": "findPatient", "arguments": {"phone": "+59899123456"}}, 5
    )
    assert looked_up.error is None and looked_up.output == {"patient": {"id": "p1", "name": "Ana Ruiz"}}
    assert faked_api[-1].headers["authorization"] == "Bearer the-key"

    collected = await fleet.tool(
        context.call, agent, {"call_id": "c2", "name": "collect", "arguments": {"name": "Ana"}}, 5
    )
    assert collected.output == {"saved": ["name"], "missing": ["reason"], "complete": True}
    await until(lambda: "Every required field is in" in (prompt("view") or ""))
    assert any(c.type == "state.set" and c.data["state"] == {"name": "Ana"} for c in commands)

    ended = CallEnded(reason="agent_hung_up", ended_by="agent", ended_at=time.time(), duration_s=12.0)
    await writing.write("call.ended", ended)
    await writing.close(5)
    await until(lambda: any(request.url.path == "/calls" for request in faked_api))
    posted = json.loads(next(request for request in faked_api if request.url.path == "/calls").content)
    assert posted["fields"] == {"name": "Ana"} and posted["complete"] is True and posted["from"] == "+59899123456"
    await fleet.sealed(context.call, SealCallRequest(usage=[], outcome="done"))
    following.cancel()
    await asyncio.gather(following, return_exceptions=True)


async def test_a_save_in_the_sandbox_is_heard_by_the_call_already_open(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient, faked_api: list[httpx.Request]
) -> None:
    """Trying the agent, a person changes its instructions: the call open takes them, its next turn runs on them."""
    await made(gateway, tenant, agent)
    context = a_voice_call(tenant, agent)
    ours = gateway.app.state.studio.sockets[(tenant.org, Env.sandbox)].socket.id
    await fleet.open(OpenCallRequest(agent=agent, context=context, app=ours))
    commands: list[Command] = []

    async def follow() -> None:
        async for command in fleet.commands(context.call):
            commands.append(command)

    following = asyncio.create_task(follow())
    writing = Writing(partial(fleet.append_many, context.call), context.call)
    writing.open()
    started = CallStarted.model_validate(
        {
            "channel": "web",
            "direction": "inbound",
            "from": "+59899123456",
            "to": agent,
            "caller": None,
            "started_at": time.time(),
        }
    )
    await writing.write("call.started", started)

    def identity() -> str:
        sent = [c.data["text"] for c in commands if c.type == "prompt.set" and c.data["name"] == "identity"]
        return sent[-1] if sent else ""

    await until(lambda: identity().startswith("You answer the phone for Clínica Norte."))
    before = len([c for c in commands if c.type == "tools.set"])
    changed = clinic(instructions="Answer in one short line, for the clinic.").model_dump(
        mode="json", exclude_none=True
    )
    saved = await gateway.http.put(f"/v1/studio/agents/{agent}", json={"definition": changed}, headers=tenant.person)
    assert saved.status_code == 200, saved.text
    await until(lambda: identity().startswith("Answer in one short line, for the clinic."))
    # The tools are sent again with it: a tool added in the save is one the open call may call.
    assert len([c for c in commands if c.type == "tools.set"]) > before

    await writing.write(
        "call.ended", CallEnded(reason="agent_hung_up", ended_by="agent", ended_at=time.time(), duration_s=3.0)
    )
    await writing.close(5)
    await fleet.sealed(context.call, SealCallRequest(usage=[], outcome="done"))
    following.cancel()
    await asyncio.gather(following, return_exceptions=True)


async def test_a_save_is_held_at_once_and_a_stopped_agent_is_let_go(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The next call runs on the new release; Stop on the Apps screen lets the gateway's socket go."""
    await made(gateway, tenant, agent)
    holder = gateway.app.state.studio
    socket = holder.sockets[(tenant.org, Env.sandbox)]
    changed = clinic(instructions="Briefly, for the clinic.").model_dump(mode="json", exclude_none=True)
    await gateway.http.put(f"/v1/studio/agents/{agent}", json={"definition": changed}, headers=tenant.person)
    await until(lambda: socket.agents[agent].instructions == "Briefly, for the clinic.")
    stopped = await gateway.http.post(f"/v1/hosted/{agent}/stop", headers=tenant.person)
    assert stopped.status_code == 204
    registry = gateway.app.state.registry
    await until(lambda: not registry.is_held(tenant.org, agent))
