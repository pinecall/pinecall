"""A page's tokens, and the agent writing first: an SMS, an email and the thread its contact's reply continues."""

import asyncio
import json
import os
import secrets
import time
from dataclasses import dataclass, field

import httpx
import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from websockets.asyncio.client import ClientConnection

from runtime.compliance.service import dial_guards
from runtime.compliance.service.dial_guards import Guards
from runtime.enums import Channel, Env
from runtime.kit.crypto import Vault
from runtime.kit.text import JsonObject
from runtime.live.service.whatsapp import Threads
from runtime.mail import service as mail
from runtime.telephony import service as telephony
from runtime.telephony.repository import RouteRepository, RouteToWrite
from runtime.telephony.service import accounts
from runtime.telephony.service.email_account import EmailAccount
from runtime.telephony.service.twilio_carrier import TwilioCarrier
from runtime.telephony.service.whatsapp_number import WhatsappNumber
from runtime.wire.dispatch import Dispatch
from tests.conftest import Gateway, Tenant, holding, needs_the_services, received
from tests.fakes import acme
from tests.fakes.internet import Internet
from tests.fakes.twilio import Twilio
from tests.telephony.service.test_email_message import an_email


def claims_of(token: str) -> JsonObject:
    """What a token says, unverified: the gateway signs it, the test only reads it."""
    claims: JsonObject = jwt.decode(token, options={"verify_signature": False})
    return claims


@needs_the_services
async def test_a_page_is_seated_with_its_own_attributes_and_its_contact_and_reads_its_log_as_itself(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The attributes are published as given, the contact is the participant's metadata, and the log token is
    the same identity, so the events the page sends come back to it."""
    async with holding(gateway, tenant, agent):
        minted = await gateway.http.post(
            "/v1/tokens",
            json={"agent": agent, "scope": "chat", "contact": "c_1", "participant_attributes": {"plan": "pro"}},
            headers=tenant.person,
        )
    assert minted.status_code == 201, minted.text
    seat = claims_of(minted.json()["participant_token"])
    reading = claims_of(minted.json()["log_token"])
    assert seat["attributes"]["plan"] == "pro"
    assert seat["metadata"] == "c_1"
    assert reading["sub"] == seat["sub"]


def dispatch_of(room_token: str) -> Dispatch:
    """The dispatch a room token carries to the worker that takes its call."""
    config = claims_of(room_token)["roomConfig"]
    return Dispatch.parse(config["agents"][0]["metadata"])


# A visitor is the same visitor in every conversation their browser opens: the token their first one
# answered names them, and is answered again. Their browser rides the dispatch, with its country.
@needs_the_services
async def test_a_visitor_token_is_the_same_visitor_in_a_new_conversation_and_the_browser_rides_the_dispatch(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """A second ticket asked with the first's visitor token seats the same visitor in a new call."""
    browser = {"visitor_ip": "181.47.10.5", "user_agent": "Mozilla/5.0 (iPhone) Safari/605.1.15"}
    async with holding(gateway, tenant, agent):
        first = await gateway.http.post(
            "/v1/tokens", json={"agent": agent, "scope": "chat", **browser}, headers=tenant.person
        )
        assert first.status_code == 201, first.text
        kept = first.json()["visitor_token"]
        again = await gateway.http.post(
            "/v1/tokens", json={"agent": agent, "scope": "chat", "visitor_token": kept}, headers=tenant.person
        )
        assert again.status_code == 201, again.text
        forged = await gateway.http.post(
            "/v1/tokens", json={"agent": agent, "scope": "chat", "visitor_token": "web_someone"}, headers=tenant.person
        )
    one, two, other = (claims_of(answer.json()["participant_token"])["sub"] for answer in (first, again, forged))
    assert one.startswith("web_") and one == two, "the visitor token names the same visitor"
    assert first.json()["call"] != again.json()["call"], "in a conversation of its own"
    assert other not in (one, two), "a token the gateway never signed names nobody"
    carried = dispatch_of(first.json()["participant_token"])
    assert carried.visitor is not None
    assert (carried.visitor.ip, carried.visitor.user_agent) == ("181.47.10.5", "Mozilla/5.0 (iPhone) Safari/605.1.15")
    assert dispatch_of(again.json()["participant_token"]).visitor is None, "a ticket that said no browser carries none"


# A test room's own voice is asked for at the token and carried to the worker in its dispatch.
@needs_the_services
async def test_a_room_token_carries_the_values_in_its_dispatch_and_asks_for_nothing_it_may_not(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The sandbox's token takes a voice; another knob is refused with the reason."""
    async with holding(gateway, tenant, agent):
        taken = await gateway.http.post(
            "/v1/tokens",
            json={"agent": agent, "scope": "talk", "tuning": {"voice": "lucia"}},
            headers=tenant.person,
        )
        assert taken.status_code == 201, taken.text
        refused = await gateway.http.post(
            "/v1/tokens",
            json={"agent": agent, "scope": "talk", "tuning": {"record": False}},
            headers=tenant.person,
        )
        assert refused.status_code == 400, refused.text
    assert "record" in json.dumps(refused.json())
    assert Dispatch(tuning={"voice": "lucia"}).dump() == '{"tuning":{"voice":"lucia"}}'


# ── the agent writes first ──


async def entries_until(gateway: Gateway, tenant: Tenant, call: str, kind: str) -> list[JsonObject]:
    """The call's durable entries, once one of this kind is among them."""
    deadline = time.monotonic() + 5.0
    while True:
        answer = await gateway.http.get(f"/v1/calls/{call}/events", params={"durable": True}, headers=tenant.person)
        entries: list[JsonObject] = list(answer.json()["entries"])
        if any(entry["type"] == kind for entry in entries):
            return entries
        assert time.monotonic() < deadline, f"call {call} never said {kind}: {[entry['type'] for entry in entries]}"
        await asyncio.sleep(0.05)


@needs_the_services
async def test_an_agent_writes_first_on_a_conversation_that_greets_nobody_and_its_second_text_is_one_more_message(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A cold text opens an outbound SMS call whose first turn is the words given; the next is said on the same call."""
    twilio, number, contact = Twilio(), f"+1555{secrets.randbelow(10**7):07d}", f"+5989{secrets.randbelow(10**7):07d}"
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    carrier = TwilioCarrier(org=tenant.org, account_sid=twilio.account_sid, user=twilio.user, secret=twilio.secret)
    route = RouteToWrite(
        org=tenant.org, number=number, agent=agent, channel=Channel.sms, env=Env.sandbox, account=twilio.account_sid
    )
    async with holding(gateway, tenant, agent):
        async with sessions.begin() as session:
            await accounts.put_carrier(session, vault, carrier)
            await RouteRepository(session).put(route)
            await dial_guards.put_guards(session, tenant.org, Guards(dial_anywhere=True))
        door = f"/v1/agents/{agent}/text"
        asked = {"to": contact, "text": "Tu turno es mañana a las 9:30."}
        sent = await gateway.http.post(door, json=asked, headers=tenant.person)
        assert sent.status_code == 202, sent.text
        texted = sent.json()
        assert (texted["from"], texted["to"], texted["env"]) == (number, contact, "sandbox")
        entries = await entries_until(gateway, tenant, texted["call"], "turn.agent")
        started = next(entry["data"] for entry in entries if entry["type"] == "call.started")
        assert (started["channel"], started["direction"], started["medium"]) == ("sms", "outbound", "text")
        said = [entry["data"]["text"] for entry in entries if entry["type"] == "turn.agent"]
        assert said == ["Tu turno es mañana a las 9:30."], "the words given open the conversation: nothing greets"
        again = await gateway.http.post(door, json={**asked, "text": "Avisanos si cambia."}, headers=tenant.person)
        assert again.status_code == 202 and again.json()["call"] == texted["call"], again.text
        other = await gateway.http.post(door, json={**asked, "from": "+15550000000"}, headers=tenant.person)
        assert other.status_code == 400 and "answers SMS at" in other.text


# ── the agent writes the first email ──


@dataclass
class Sent:
    """Every email the agents sent through the tenant's mailbox, in the order they left."""

    emails: list[mail.Email] = field(default_factory=list[mail.Email])

    async def wait_for(self, count: int, within_s: float = 30.0) -> list[mail.Email]:
        """The emails once there are this many: the first answer waits for an app that never opens its call."""
        deadline = time.monotonic() + within_s
        while len(self.emails) < count:
            assert time.monotonic() < deadline, f"{len(self.emails)} emails left, not {count}"
            await asyncio.sleep(0.05)
        return self.emails


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Sent:
    """The mailbox's SMTP server, in the test's hands: what it was handed, never refused."""
    taken = Sent()

    async def send_email(account: telephony.EmailAccount, email: mail.Email) -> None:
        taken.emails.append(email)

    monkeypatch.setattr(telephony, "send_email", send_email)
    return taken


async def a_mailbox(sessions: async_sessionmaker[AsyncSession], tenant: Tenant, agent: str) -> str:
    """A mailbox of the tenant's whose address answers email for the agent in the sandbox; its address."""
    address = f"help-{secrets.token_hex(3)}@acme.example"
    account = EmailAccount(
        org=tenant.org, address=address, password="p", imap_host="mail.acme.example", smtp_host="mail.acme.example"
    )
    route = RouteToWrite(
        org=tenant.org, number=address, agent=agent, channel=Channel.email, env=Env.sandbox, account=address
    )
    async with sessions.begin() as session:
        await accounts.put_carrier(session, Vault(os.environ["PINECALL_VAULT_KEY"]), account)
        await RouteRepository(session).put(route)
        await dial_guards.put_guards(session, tenant.org, Guards(dial_anywhere=True))
    return address


async def configure(app: ClientConnection, agent: str) -> None:
    """The agent greets every call with fixed words, and thinks with acme."""
    declared = {"config": {"greeting": {"say": GREETING}, "llm": {"provider": acme.ACME, "model": acme.MODEL}}}
    await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": declared}))
    await received(app, "agent.configured")


GREETING = "Buenas, Brightside Dental."


@needs_the_services
async def test_the_agents_first_email_opens_a_thread_its_contacts_reply_continues_on_the_same_call(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession], sent: Sent
) -> None:
    """Sent from the routed address under our own id; the reply names it, and the agent answers it on that call."""
    async with holding(gateway, tenant, agent) as app:
        await configure(app, agent)
        address = await a_mailbox(sessions, tenant, agent)
        door = f"/v1/agents/{agent}/text"
        asked = {"to": "Ana@Example.org", "subject": "Tu turno", "text": "Ana, tu turno es mañana a las 9:30."}
        answer = await gateway.http.post(door, json=asked, headers=tenant.person)
        assert answer.status_code == 202, answer.text
        texted = answer.json()
        assert (texted["from"], texted["to"]) == (address, "ana@example.org")
        (first,) = await sent.wait_for(1)
        ours = first.headers["Message-ID"]
        assert (first.to, first.subject, first.text) == ("ana@example.org", "Tu turno", asked["text"])
        assert ours.endswith("@acme.example>") and "In-Reply-To" not in first.headers
        assert first.headers["Auto-Submitted"] == "auto-generated", "it answers nothing (RFC 3834 §5)"
        entries = await entries_until(gateway, tenant, texted["call"], "turn.agent")
        started = next(entry["data"] for entry in entries if entry["type"] == "call.started")
        assert (started["channel"], started["direction"]) == ("email", "outbound")
        assert started["metadata"] == {"email_thread": ours, "subject": "Tu turno"}
        headers = {"Message-ID": "<r1@example.org>", "In-Reply-To": ours, "References": ours, "Subject": "Re: Tu turno"}
        reply = telephony.read_email(an_email("¿Puedo a las 10?", To=address, **headers), address, "<f@x>")
        assert reply is not None and reply.thread == ours
        threads: Threads = gateway.state["whatsapp_threads"]
        assert await threads.receive(reply)
        answered = (await sent.wait_for(2))[1]
        assert (answered.subject, answered.headers["In-Reply-To"]) == ("Re: Tu turno", "<r1@example.org>")
        assert answered.headers["References"] == f"{ours} <r1@example.org>"
        assert answered.text == "acme heard: ¿Puedo a las 10?"
        entries = await entries_until(gateway, tenant, texted["call"], "turn.user")
        said = [entry["data"]["text"] for entry in entries if entry["type"] == "turn.agent"]
        assert said == [asked["text"], "acme heard: ¿Puedo a las 10?"], "the reply is answered on the same call"


@needs_the_services
async def test_an_email_with_no_words_given_is_written_by_the_agent_on_what_it_is_for(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession], sent: Sent
) -> None:
    """As a dialled call with no greeting opens: the model writes, on the instruction, with the metadata on the call."""
    async with holding(gateway, tenant, agent) as app:
        await configure(app, agent)
        await a_mailbox(sessions, tenant, agent)
        door = f"/v1/agents/{agent}/text"
        aviso = {"aviso": {"id": 7, "barrio": "Pocitos"}}
        asked = {"to": "ana@example.org", "subject": "Un aviso", "metadata": aviso, "instruction": "Contale del aviso."}
        answer = await gateway.http.post(door, json=asked, headers=tenant.person)
        assert answer.status_code == 202, answer.text
        (first,) = await sent.wait_for(1)
        assert first.subject == "Un aviso" and first.text.startswith("acme heard:"), (
            "the model wrote it, not the greeting"
        )
        entries = await entries_until(gateway, tenant, answer.json()["call"], "turn.agent")
        started = next(entry["data"] for entry in entries if entry["type"] == "call.started")
        metadata = started["metadata"]
        assert {**aviso, "instruction": "Contale del aviso.", "subject": "Un aviso"}.items() <= metadata.items()
        assert metadata["email_thread"] == first.headers["Message-ID"]
        refused = await gateway.http.post(door, json={**asked, "subject": None}, headers=tenant.person)
        assert refused.status_code == 400 and "needs a `subject`" in refused.text
        no_words = await gateway.http.post(door, json={"to": "+59899000001"}, headers=tenant.person)
        assert no_words.status_code == 400 and "an SMS needs its `text`" in no_words.text


# An email the contact wrote is answered by one email: the class's greeting went out first, alone, and
# the answer after it (2026-11-23, every agent with a greeting answered every first email twice).
@needs_the_services
async def test_an_email_the_contact_wrote_is_answered_by_one_email_and_nothing_greets_before_it(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession], sent: Sent
) -> None:
    async with holding(gateway, tenant, agent) as app:
        await configure(app, agent)
        address = await a_mailbox(sessions, tenant, agent)
        written = telephony.read_email(
            an_email(To=address, **{"Message-ID": f"<{secrets.token_hex(4)}@example.org>"}), address, "<f@x>"
        )
        assert written is not None
        threads: Threads = gateway.state["whatsapp_threads"]
        assert await threads.receive(written)
        (answer,) = await sent.wait_for(1)
        assert answer.text == "acme heard: Hola, ¿abren el sábado?", "the first email out is the answer"
        await asyncio.sleep(1.0)
        assert [email.text for email in sent.emails] == [answer.text], "and the only one"


@needs_the_services
async def test_the_sandbox_answers_a_whatsapp_template_as_simulated_and_writes_to_nobody(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The door a server's key sends a template through: in the sandbox, 202, `simulated`, no id, no number needed."""
    asked = {"to": "+5491155550134", "template": "consulta_derivada", "language": "es_AR", "variables": ["Juan Cruz"]}
    door = f"/v1/agents/{agent}/template"
    async with holding(gateway, tenant, agent):
        sent = await gateway.http.post(door, json=asked, headers=tenant.person)
        assert sent.status_code == 202, sent.text
        assert sent.json() == {
            "agent": agent,
            "to": "+5491155550134",
            "from": None,
            "env": "sandbox",
            "template": "consulta_derivada",
            "simulated": True,
            "message_id": None,
            "call": None,
        }
        refused = await gateway.http.post(door, json={**asked, "to": "1155"}, headers=tenant.person)
        assert refused.status_code == 400, refused.text


@needs_the_services
async def test_a_template_with_its_words_opens_the_contacts_conversation_and_the_sandbox_asks_meta_nothing(
    gateway: Gateway, tenant: Tenant, agent: str, sessions: async_sessionmaker[AsyncSession], internet: Internet
) -> None:
    """The words are the first turn of an outbound WhatsApp call, with its metadata; the next words go on it too."""
    number, contact = f"+1555{secrets.randbelow(10**7):07d}", f"+5491{secrets.randbelow(10**9):09d}"
    meta_id, vault = f"10{secrets.randbelow(10**9):09d}", Vault(os.environ["PINECALL_VAULT_KEY"])
    at_meta = WhatsappNumber(org=tenant.org, phone_number_id=meta_id, access_token="the org's token")
    route = RouteToWrite(
        org=tenant.org, number=number, agent=agent, channel=Channel.whatsapp, env=Env.sandbox, account=meta_id
    )
    asked_of_meta: list[str] = []

    def graph(request: httpx.Request) -> httpx.Response:
        asked_of_meta.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json={"messages": [{"id": "wamid.never"}]})

    words = "Hola Marta, recibimos tu consulta por la casa de Olazaval al 400. ¿Coordinamos una visita?"
    asked = {"to": contact, "template": "visit_request", "language": "es_AR", "variables": ["Marta"], "text": words}
    with internet.serving("graph.facebook.com", graph):
        async with holding(gateway, tenant, agent):
            async with sessions.begin() as session:
                await accounts.put_carrier(session, vault, at_meta)
                await RouteRepository(session).put(route)
            door = f"/v1/agents/{agent}/template"
            sent = await gateway.http.post(
                door, json={**asked, "metadata": {"listing": 2821756}}, headers=tenant.person
            )
            assert sent.status_code == 202, sent.text
            said = sent.json()
            assert (said["from"], said["simulated"], said["message_id"]) == (number, True, None)
            entries = await entries_until(gateway, tenant, said["call"], "turn.agent")
            started = next(entry["data"] for entry in entries if entry["type"] == "call.started")
            assert (started["channel"], started["direction"], started["medium"]) == ("whatsapp", "outbound", "text")
            assert started["metadata"]["listing"] == 2821756
            assert [entry["data"]["text"] for entry in entries if entry["type"] == "turn.agent"] == [words]
            again = await gateway.http.post(door, json={**asked, "text": "Una cosa más."}, headers=tenant.person)
            assert again.json()["call"] == said["call"], "the contact's answer lands on the conversation going"
            # The contact never wrote: Meta takes a template alone, so the words go as one, and the agent is
            # told of them on the conversation (on 2026-11-27 a second lead's message was refused there).
            entries = await entries_until(gateway, tenant, said["call"], "supervisor.whispered")
            told = [entry["data"]["text"] for entry in entries if entry["type"] == "supervisor.whispered"]
            assert len(told) == 1 and "Una cosa más." in told[0]
            assert [entry["data"]["text"] for entry in entries if entry["type"] == "turn.agent"] == [words]
    assert asked_of_meta == [], "the sandbox asks Meta for no template, and the first words are sent by nobody"
