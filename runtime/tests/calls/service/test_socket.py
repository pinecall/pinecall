"""An app's socket: busy, not closed, when the database does not answer; its routes checked when it registers."""

import asyncio
import json
import os
import secrets
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.service.live import Live
from pinecall_runtime.calls.service.peers import APP_CHANNEL
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.calls.service.socket import BUSY, AppSocket
from pinecall_runtime.calls.service.threads import Threads
from pinecall_runtime.channels import service as channels
from pinecall_runtime.channels.models import Route as RouteRow
from pinecall_runtime.config import load_settings
from pinecall_runtime.enums import Channel, Env, KeyScope, RouteOrigin
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.postgres import create_engine, session_maker
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.commands import AgentRegister
from pinecall_runtime.wire.parts import Route
from pinecall_runtime.wire.signal import ForApp
from tests.conftest import Gateway, Tenant, holding, needs_the_database, needs_the_services, received, until

pytestmark = needs_the_database

AN_APP = Actor(key_id="k_app", org="org_acme", env=Env.sandbox, scopes=frozenset({KeyScope.app}))
REGISTER: JsonObject = {
    "type": "agent.register",
    "agent": "recepcion",
    "call": None,
    "id": "r1",
    "data": {"routes": []},
}


class _Registry:
    """A registry holding nothing: every frame is answered down the socket alone."""

    holders: dict[object, object] = {}

    def on_socket(self, app: str, env: Env, slug: str) -> None:
        return None

    def slugs_of(self, org: str) -> frozenset[str]:
        return frozenset()


# On 2026-10-21 a pool with no connection free cut an app's socket at the frame it was sending.
# The one connection of this pool is held for the whole frame, as every connection was then.
@pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="the test database")
async def test_a_frame_the_database_did_not_answer_is_refused_as_busy_and_the_socket_stays() -> None:
    engine = create_engine(load_settings(), pool_size=1)
    sessions = session_maker(engine)
    sent: list[JsonObject] = []
    closed: list[str] = []

    async def send(frame: JsonObject) -> None:
        sent.append(frame)

    async def close(why: str) -> None:
        closed.append(why)

    handles = SimpleNamespace(sessions=sessions)
    serving = cast(Serving, SimpleNamespace(handles=handles, live=Live(), registry=_Registry()))
    socket = AppSocket(serving, cast(Threads, None), AN_APP, send, close, None)
    try:
        async with sessions.begin() as held:
            await held.execute(text("select 1"))
            await asyncio.wait_for(socket.take(REGISTER), timeout=10)
    finally:
        await engine.dispose()
    [error] = sent
    assert error["type"] == "error"
    data = cast(JsonObject, error["data"])
    assert data["code"] == BUSY and data["recoverable"] is True
    assert (data["command"], data["id"]) == ("agent.register", "r1")
    assert "no connection came free" in str(data["message"])
    assert closed == []


# What another gateway tells a socket arrives on its inbox; a message that cannot be read, or applied,
# ended the loop that heard it, and the socket was deaf for its whole life (it is said now).
async def test_a_message_of_the_inbox_that_cannot_be_read_does_not_leave_the_socket_deaf() -> None:
    sent: list[JsonObject] = []

    async def send(frame: JsonObject) -> None:
        sent.append(frame)

    async def close(_why: str) -> None:
        return None

    live = Live()
    serving = cast(Serving, SimpleNamespace(live=live, registry=_Registry()))
    socket = AppSocket(serving, cast(Threads, None), AN_APP, send, close, None)
    listening = asyncio.create_task(socket.listen())
    try:
        await asyncio.wait_for(socket.listening.wait(), 5)
        live.signal.publish(APP_CHANNEL.format(app=socket.id), b"this is not a message for a socket")
        told = Entry.unstored("recepcion", "error", {"code": "killed", "message": "x", "recoverable": False})
        live.signal.publish(APP_CHANNEL.format(app=socket.id), ForApp(entry=told).model_dump_json().encode())
        await until(lambda: bool(sent))
        assert sent[0]["type"] == "error"
        assert not listening.done()
    finally:
        listening.cancel()
        await asyncio.gather(listening, return_exceptions=True)


# A number reaches an agent once the org routed it, never through a registration: agent.registered says
# what the agent answers (web, and the numbers routed to it), and a number the app names that the org
# never routed to it is refused with the verb that routes it.
@needs_the_services
async def test_agent_registered_says_the_routes_the_agent_answers_and_refuses_one_it_was_never_given(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    number = f"+3491{secrets.randbelow(10**7):07d}"
    route = RouteRow(org=tenant.org, agent=agent, channel=Channel.phone, number=number, env=Env.sandbox, managed=False)
    async with sessions.begin() as session:
        await channels.put_route(session, route, channels.RouteWrite(origin=RouteOrigin.typed))
    async with gateway.socket("/v1/apps", tenant.server) as app:
        both = [Route(channel=Channel.web, number=None), Route(channel=Channel.phone, number=number)]
        wanted = AgentRegister(routes=both)
        await app.send(json.dumps({"type": "agent.register", "agent": agent, "call": None, "data": wanted.dump()}))
        registered = await received(app, "agent.registered")
        answered = [(found["channel"], found["number"]) for found in registered["data"]["routes"]]
        assert answered == [("web", None), ("phone", number)]

        never = AgentRegister(routes=[Route(channel=Channel.phone, number="+15550000000")])
        other = f"{agent}-other"
        await app.send(json.dumps({"type": "agent.register", "agent": other, "call": None, "data": never.dump()}))
        refused = await received(app, "error")
        assert "+15550000000 on phone is not a route of" in refused["data"]["message"]
        assert "pinecall numbers import" in refused["data"]["message"]


# The session writes end_call's result itself: an answer from the app would be a second result, which
# could arrive first and tell the model the tool does not exist.
@needs_the_services
async def test_an_apps_answer_to_end_call_is_refused_and_never_written(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent) as app:
        answer = {"call_id": "tc_1", "name": "end_call", "error": "this app declares no tool called end_call"}
        await app.send(json.dumps({"type": "tool.result", "agent": agent, "call": "call_nobody", "data": answer}))
        refused = await received(app, "error")
    assert "end_call is the platform's own tool" in refused["data"]["message"]


# What cannot run is refused when it is declared: a model on a vendor nobody keyed closed the first call
# with a 4503 instead, long after the app was told its declaration was taken.
@needs_the_services
async def test_a_declared_model_on_a_vendor_nobody_keyed_is_refused_at_configure(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent) as app:
        unkeyed = {"config": {"llm": {"provider": "openai", "model": "gpt-5.4-mini"}}}
        await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": unkeyed}))
        refused = await received(app, "error")
    assert "openai has no key: the org brought none and the box holds none" in refused["data"]["message"]
