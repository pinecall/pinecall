"""The gateway holding a Studio agent: registered on its own socket, refused to anyone else, its calls answered."""

import asyncio
import json
import time
from datetime import date

import httpx

from runtime.calls.context import CallContext, Route, dump_context, new_call_id
from runtime.enums import Channel, Direction, Env
from runtime.hosting import service as hosting
from runtime.jobs.service.call_client import CallClient, open_call
from runtime.jobs.service.client import GatewayClient
from runtime.session.call import ToolUse
from runtime.session.writing import Writing
from runtime.wire.base import Command
from runtime.wire.commands import AgentRegister
from runtime.wire.events import CallEnded, CallStarted, ToolCall
from runtime.wire.parts import ToolResult
from runtime.wire.worker import OpenCallRequest
from tests.conftest import Gateway, Tenant, needs_the_services, received, until
from tests.studio.factories import clinic, live_of, made, socket_here

pytestmark = needs_the_services


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


async def opened_here(fleet: GatewayClient, gateway: Gateway, tenant: Tenant, agent: str) -> CallClient:
    """A call of the agent opened by a worker and bound to this gateway's Studio socket, its start written."""
    context = a_voice_call(tenant, agent)
    opening = {"agent": agent, "context": dump_context(context), "app": socket_here(gateway, tenant).id}
    return await open_call(fleet, OpenCallRequest.model_validate(opening))


def started(agent: str) -> CallStarted:
    """The call's first entry, as its session writes it."""
    said = {
        "channel": "web",
        "direction": "inbound",
        "from": "+59899123456",
        "to": agent,
        "caller": None,
        "started_at": time.time(),
    }
    return CallStarted.model_validate(said)


def hung_up(after_s: float) -> CallEnded:
    """The agent ended the call."""
    return CallEnded(reason="agent_hung_up", ended_by="agent", ended_at=time.time(), duration_s=after_s)


class Following:
    """The commands a call's app sends it, kept as they come."""

    def __init__(self, link: CallClient) -> None:
        """Following from now on."""
        self.commands: list[Command] = []
        self.task = asyncio.create_task(self._follow(link))

    async def _follow(self, link: CallClient) -> None:
        async for command in link.commands():
            self.commands.append(command)

    def prompt(self, name: str) -> str | None:
        """The block of the prompt last set under this name."""
        sent = [str(c.data["text"]) for c in self.commands if c.type == "prompt.set" and c.data["name"] == name]
        return sent[-1] if sent else None

    async def stop(self) -> None:
        """Follow no more."""
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


async def test_a_studio_agent_is_held_by_the_gateway_and_listed_as_its_process(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """Made in Studio, it is held at once, by the process the console names Pinecall Studio."""
    await made(gateway, tenant, agent)
    processes = (await gateway.http.get("/v1/apps", headers=tenant.person)).json()
    assert any(agent in json.dumps(item) and "pinecall-studio" in json.dumps(item) for item in processes["apps"])
    # The agents list says what it is, so the console draws Studio for it and not for a class.
    listed = (await gateway.http.get("/v1/agents", headers=tenant.person)).json()["agents"]
    assert next(row["kind"] for row in listed if row["slug"] == agent) == "studio"


async def test_an_app_registering_a_studio_agents_slug_is_refused(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """A slug is one agent: a terminal's `pinecall start` of the same name is told it is Studio's."""
    await made(gateway, tenant, agent)
    async with gateway.socket("/v1/apps", tenant.server) as app:
        register = AgentRegister(routes=[]).model_dump(mode="json")
        await app.send(json.dumps({"type": "agent.register", "agent": agent, "call": None, "data": register}))
        refused = await received(app, "error")
    assert "Studio agent" in refused["data"]["message"]


async def test_a_call_is_answered_from_the_definition_its_tools_run_and_its_results_posted(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient, agenda: list[httpx.Request]
) -> None:
    """The prompt rendered for the caller, the lookup sent, collect saving the name, the fields posted at the end."""
    await made(gateway, tenant, agent)
    link = await opened_here(fleet, gateway, tenant, agent)
    following = Following(link)
    writing = Writing(link.append_many, link.call)
    writing.open()
    await writing.write("call.started", started(agent))

    # The blocks go out in order, identity, tools, view: the last one landed is all of them.
    await until(lambda: following.prompt("view") is not None)
    identity = following.prompt("identity") or ""
    assert identity.startswith("You answer the phone for Clínica Norte. The caller dials from +59899123456.")
    assert "<protocols>" in identity
    assert (following.prompt("tools") or "").startswith("<tools>\n- findPatient: Finds the patient by phone.")
    assert "Still to collect" in (following.prompt("view") or "")

    looked_up = await link.run_tool(ToolUse("c1", "findPatient", {"phone": "+59899123456"}), None)
    assert looked_up.error is None and looked_up.output == {"patient": {"id": "p1", "name": "Ana Ruiz"}}
    assert agenda[-1].headers["authorization"] == "Bearer the-key"

    collected = await link.run_tool(ToolUse("c2", "collect", {"name": "Ana"}), None)
    assert collected.output == {"saved": ["name"], "missing": ["reason"], "complete": True}
    await until(lambda: "Every required field is in" in (following.prompt("view") or ""))
    assert any(c.type == "state.set" and c.data["state"] == {"name": "Ana"} for c in following.commands)

    await writing.write("call.ended", hung_up(12.0))
    await writing.close(5)
    await until(lambda: any(request.url.path == "/calls" for request in agenda))
    posted = json.loads(next(request for request in agenda if request.url.path == "/calls").content)
    assert posted["fields"] == {"name": "Ana"} and posted["complete"] is True and posted["from"] == "+59899123456"
    await link.seal([], "done")
    await following.stop()
    await link.aclose()


async def test_the_hang_ups_tool_call_is_the_sessions_to_answer_and_the_agent_adds_no_second_result(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient, agenda: list[httpx.Request]
) -> None:
    """The model ends the call: the session writes end_call's call and result, and Studio answers neither."""
    await made(gateway, tenant, agent)
    link = await opened_here(fleet, gateway, tenant, agent)
    following = Following(link)
    writing = Writing(link.append_many, link.call)
    writing.open()
    await writing.write("call.started", started(agent))
    await until(lambda: following.prompt("identity") is not None)
    await writing.write("tool.call", ToolCall(call_id="e1", name="end_call", arguments={}, speech_id=None))
    # Entries are read in order: once collect is answered, Studio has seen end_call's call and let it be.
    await link.run_tool(ToolUse("c1", "collect", {"name": "Ana"}), None)
    await writing.write("tool.result", ToolResult(call_id="e1", name="end_call"))
    await writing.flush(5)
    page = await gateway.http.get(
        f"/v1/calls/{link.call}/events", params={"types": "tool.result"}, headers=tenant.server
    )
    results = [entry["data"] for entry in page.json()["entries"] if entry["data"]["call_id"] == "e1"]
    assert len(results) == 1 and results[0].get("error") is None
    await writing.write("call.ended", hung_up(3.0))
    await writing.close(5)
    await link.seal([], "done")
    await following.stop()
    await link.aclose()
    del agenda


async def test_a_save_in_the_sandbox_is_heard_by_the_call_already_open(
    gateway: Gateway, tenant: Tenant, agent: str, fleet: GatewayClient, agenda: list[httpx.Request]
) -> None:
    """Trying the agent, a person changes its instructions: the call open takes them, its next turn runs on them."""
    await made(gateway, tenant, agent)
    link = await opened_here(fleet, gateway, tenant, agent)
    following = Following(link)
    writing = Writing(link.append_many, link.call)
    writing.open()
    await writing.write("call.started", started(agent))

    def identity() -> str:
        return following.prompt("identity") or ""

    await until(lambda: identity().startswith("You answer the phone for Clínica Norte."))
    before = len([c for c in following.commands if c.type == "tools.set"])
    changed = clinic(instructions="Answer in one short line, for the clinic.").model_dump(
        mode="json", exclude_none=True
    )
    saved = await gateway.http.put(f"/v1/studio/agents/{agent}", json={"definition": changed}, headers=tenant.person)
    assert saved.status_code == 200, saved.text
    await until(lambda: identity().startswith("Answer in one short line, for the clinic."))
    # The tools are sent again with it: a tool added in the save is one the open call may call.
    assert len([c for c in following.commands if c.type == "tools.set"]) > before

    await writing.write("call.ended", hung_up(3.0))
    await writing.close(5)
    await link.seal([], "done")
    await following.stop()
    await link.aclose()
    del agenda


async def test_a_save_is_held_at_once_and_a_stopped_agent_is_let_go(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The next call runs on the new release; Stop on the Apps screen lets the gateway's socket go."""
    await made(gateway, tenant, agent)
    socket = socket_here(gateway, tenant)
    changed = clinic(instructions="Briefly, for the clinic.").model_dump(mode="json", exclude_none=True)
    await gateway.http.put(f"/v1/studio/agents/{agent}", json={"definition": changed}, headers=tenant.person)

    # Held once the socket took the configure: its registration is said a moment before.
    def held_as_saved() -> bool:
        definition = socket.agents.get(agent)
        return definition is not None and definition.instructions == "Briefly, for the clinic."

    await until(held_as_saved)
    stopped = await gateway.http.post(f"/v1/hosted/{agent}/stop", headers=tenant.person)
    assert stopped.status_code == 204
    holders = live_of(gateway).holders
    await until(lambda: agent not in holders.list_held(tenant.org, Env.sandbox))


# A message of the channel the saves are told on that could not even be decoded ended the listener, and no
# Studio agent saved on any gateway was held by this one again.
async def test_a_message_that_cannot_be_read_does_not_end_the_holders_listening_for_saves(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    signal = live_of(gateway).signal
    signal.publish(hosting.APPS_CHANGED, b"\xff\xfe not a name")
    signal.publish(hosting.APPS_CHANGED, b"an-org|not-an-env")
    await made(gateway, tenant, agent)
