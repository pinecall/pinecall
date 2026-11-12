"""An app's socket: busy, not closed, when the database does not answer; its routes checked when it registers."""

import asyncio
import json
import secrets

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Actor
from runtime.config import load_settings
from runtime.enums import Channel, Env, KeyScope
from runtime.kit.text import JsonObject
from runtime.live.peers import APP_INBOX
from runtime.live.service.socket import BUSY
from runtime.postgres import create_engine, session_maker
from runtime.signal import LocalSignal
from runtime.telephony.models import Route as RouteRow
from runtime.wire.base import Entry
from runtime.wire.commands import AgentRegister
from runtime.wire.events import ErrorEvent
from runtime.wire.parts import Route
from runtime.wire.signal import ForApp
from tests.conftest import Gateway, Tenant, holding, needs_the_database, needs_the_services, received, until
from tests.live.conftest import Side, a_live_side

AN_APP = Actor(key_id="k_app", org="org_acme", env=Env.sandbox, scopes=frozenset({KeyScope.app}))
REGISTER: JsonObject = {
    "type": "agent.register",
    "agent": "recepcion",
    "call": None,
    "id": "r1",
    "data": {"routes": []},
}


class Connection:
    """An app's connection as its socket writes to it: every frame sent, and why it was closed."""

    def __init__(self) -> None:
        self.sent: list[JsonObject] = []
        self.closed: list[str] = []

    async def send(self, frame: JsonObject) -> None:
        """One frame down the connection."""
        self.sent.append(frame)

    async def close(self, why: str) -> None:
        """The connection closed."""
        self.closed.append(why)


# On 2026-10-21 a pool with no connection free cut an app's socket at the frame it was sending.
# The one connection of this gateway's pool is held for the whole frame, as every connection was then.
@needs_the_database
async def test_a_frame_the_database_did_not_answer_is_refused_as_busy_and_the_socket_stays() -> None:
    engine = create_engine(load_settings(), pool_size=1)
    sessions = session_maker(engine)
    connection = Connection()
    try:
        async with a_live_side(engine, sessions, LocalSignal()) as side:
            socket = side.apps.make(AN_APP, connection.send, connection.close, "a-test")
            async with sessions.begin() as held:
                await held.execute(text("select 1"))
                await asyncio.wait_for(socket.take(REGISTER), timeout=10)
    finally:
        await engine.dispose()
    (error,) = connection.sent
    assert error["type"] == "error"
    refused = ErrorEvent.model_validate(error["data"])
    assert refused.code == BUSY and refused.recoverable is True
    assert (refused.command, refused.id) == ("agent.register", "r1")
    assert "no connection came free" in refused.message
    assert connection.closed == []


# What another gateway tells a socket arrives on its inbox; a message that cannot be read, or applied,
# ended the loop that heard it, and the socket was deaf for its whole life (it is said now).
@needs_the_database
async def test_a_message_of_the_inbox_that_cannot_be_read_does_not_leave_the_socket_deaf(side: Side) -> None:
    connection = Connection()
    socket = side.apps.make(AN_APP, connection.send, connection.close, "a-test")
    async with socket.open():
        inbox = APP_INBOX.name.format(app=socket.id)
        side.parts.signal.publish(inbox, b"this is not a message for a socket")
        told = Entry.make_unstored("recepcion", "error", {"code": "killed", "message": "x", "recoverable": False})
        side.parts.signal.publish(inbox, ForApp(entry=told).model_dump_json().encode())
        await until(lambda: bool(connection.sent))
        assert connection.sent[0]["type"] == "error"
    assert connection.closed == []


# A number reaches an agent once the org routed it, never through a registration: agent.registered says
# what the agent answers (web, and the numbers routed to it), and a number the app names that the org
# never routed to it is refused with the verb that routes it.
@needs_the_services
async def test_agent_registered_says_the_routes_the_agent_answers_and_refuses_one_it_was_never_given(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    number = f"+3491{secrets.randbelow(10**7):07d}"
    async with sessions.begin() as session:
        session.add(RouteRow(org=tenant.org, agent=agent, channel=Channel.phone, number=number, env=Env.sandbox))
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


# What a PUT of a persona refuses is refused when the class declares the caller: the sentence names
# the vendor, and the socket stays.
@needs_the_services
async def test_a_persona_the_class_declares_on_a_vendor_nobody_keyed_is_refused_at_configure(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    unkeyed = {"name": "on-openai", "goal": "book today", "style": "short", "llm": "openai/gpt-5.4-mini"}
    async with holding(gateway, tenant, agent) as app:
        declared = {"config": {"personas": {"own": [unkeyed]}}}
        await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": declared}))
        refused = await received(app, "error")
        assert "openai has no key: the org brought none and the box holds none" in refused["data"]["message"]
        declared = {"config": {"judges": {"on": ["consent"], "own": [{"name": "offers", "question": "Offered?"}]}}}
        await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": declared}))
        assert (await received(app, "agent.configured"))["data"]["changed"] == ["judges"]
