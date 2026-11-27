"""The WhatsApp threads: what a gateway hands on, a message taken up, a voice note, whose number a body reaches."""

import asyncio
import dataclasses
import json
import secrets
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.enums import Channel, Env
from runtime.kit import sms as texts
from runtime.live.parts import LiveParts
from runtime.live.peers import THREADS, ThreadKey
from runtime.live.service import whatsapp, written
from runtime.live.service.replies import ByMessenger, BySms, ByWhatsapp, Ears, FirstSaid
from runtime.live.service.whatsapp import OpenThread
from runtime.providers import service as providers
from runtime.providers.service import transcription
from runtime.telephony.repository import RouteRepository, RouteToWrite
from runtime.telephony.service import accounts, sms
from runtime.telephony.service.twilio import TwilioAccount
from runtime.telephony.service.whatsapp_number import WhatsappNumber
from runtime.whatsapp.service import messaging, webhook
from runtime.whatsapp.service.webhook import Inbound, Receipt
from runtime.wire.events import MessageStatus
from tests.conftest import Tenant, needs_the_database, until
from tests.fakes.meta import Graph, a_body, a_text
from tests.fakes.twilio import Twilio
from tests.live.conftest import Side

if TYPE_CHECKING:
    from runtime.session.session import Session

SCOPE = Scope("an org", Env.sandbox)

HEARD_WITHIN_S = 5.0


# A message another gateway handed on that could not be read raised out of the loop that heard it, and
# no thread held here was told anything from then on. That a turn which cannot be answered is said with
# its call, and the contact's next one answered, is the same `survive` around each message of a thread:
# only a database that does not answer plays it, and `kit/test_loops.py` holds `survive` to it.
@needs_the_database
async def test_a_message_another_gateway_handed_on_that_cannot_be_read_is_said_and_the_next_is_heard(
    side: Side, caplog: pytest.LogCaptureFixture
) -> None:
    handed_on = THREADS.name.format(gateway=side.parts.owners.id)
    said = f"a message between gateways failed on {handed_on}"
    # Told until it is heard: the threads listen from a moment after they start, and the signal keeps nothing.
    deadline = time.monotonic() + HEARD_WITHIN_S
    while said not in caplog.text:
        assert time.monotonic() < deadline, "the threads never heard what was handed on"
        side.parts.signal.publish(handed_on, b"this is not a message")
        await asyncio.sleep(0.02)
    before = caplog.text.count(said)
    side.parts.signal.publish(handed_on, b'{"number": 7}')
    await until(lambda: caplog.text.count(said) > before)


# ── a message of an open conversation ──


def a_thread(side: Side, http: httpx.AsyncClient, message: Inbound, *, agents_line: bool) -> OpenThread:
    """A contact's open conversation, on a call the agent may speak on or one a person took."""
    running = cast("Session", SimpleNamespace(line=SimpleNamespace(agent_may_speak=agents_line)))
    by_meta = ByWhatsapp(http, "the number's token", Ears(side.parts, SCOPE))
    return OpenThread(session=running, inbound=message, reaches=by_meta)


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What the model was asked, in place of asking it."""
    texts: list[str] = []

    async def hear(live: LiveParts, running: "Session", text: str) -> None:
        texts.append(text)

    monkeypatch.setattr(written, "hear", hear)
    return texts


@needs_the_database
@pytest.mark.parametrize("agents_line", [True, False])
async def test_a_message_taken_up_is_marked_read_and_typing_is_shown_only_while_the_model_writes(
    side: Side, asked: list[str], *, agents_line: bool
) -> None:
    """The contact sees the two blue ticks either way; "typing…" only when the model is the one answering."""
    meta = Graph()
    (message,) = webhook.messages_in(a_body(a_text("quiero un turno")))
    async with httpx.AsyncClient(transport=httpx.MockTransport(meta.answer)) as http:
        thread = a_thread(side, http, message, agents_line=agents_line)
        assert await whatsapp.take_up(side.parts, thread, message) is None
    assert meta.read == [("wamid.1", agents_line)]
    assert asked == ["quiero un turno"]


# ── a conversation a template opened ──


@needs_the_database
async def test_the_words_a_template_carried_are_not_sent_again_and_every_reply_after_them_is(side: Side) -> None:
    """The first turn of a conversation the agent opened on a template is said on the call and sent by nobody."""
    meta = Graph()
    (message,) = webhook.messages_in(a_body(a_text("sí")))
    async with httpx.AsyncClient(transport=httpx.MockTransport(meta.answer)) as http:
        words = "Hola Marta, recibimos tu consulta por la casa."
        way = FirstSaid(ByWhatsapp(http, "the number's token", Ears(side.parts, SCOPE)), words)
        await way.send(message, words)
        assert meta.sent == [], "the template was those words"
        await way.send(message, "Tiene tres dormitorios.")
        await way.send(message, words)
        await way.mark_read(message, typing=False)
        # Were the template's turn never said, the agent's first answer still reaches the contact.
        unsaid = FirstSaid(ByWhatsapp(http, "the number's token", Ears(side.parts, SCOPE)), words)
        await unsaid.send(message, "Sí, te cuento.")
    bodies = [sent["text"]["body"] for sent in meta.sent]  # type: ignore[index]
    assert bodies == ["Tiene tres dormitorios.", words, "Sí, te cuento."], (
        "only the first saying of those words is unsent"
    )
    assert meta.read == [("wamid.1", False)]


@needs_the_database
async def test_a_message_is_answered_even_when_meta_refuses_to_mark_it_read(side: Side, asked: list[str]) -> None:
    meta = Graph(refusal=(400, "message is too old to be marked read"))
    (message,) = webhook.messages_in(a_body(a_text("hola")))
    async with httpx.AsyncClient(transport=httpx.MockTransport(meta.answer)) as http:
        assert await whatsapp.take_up(side.parts, a_thread(side, http, message, agents_line=True), message) is None
    assert asked == ["hola"]


@needs_the_database
async def test_a_voice_note_is_read_as_what_it_says(
    side: Side, asked: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its audio is fetched from Meta on the number's token and heard; the model is asked its words."""
    meta = Graph(media={"media.7": (b"OggS", "audio/ogg; codecs=opus")})
    heard: list[tuple[bytes, bool]] = []

    async def transcribe(ears: object, note: transcription.Note) -> transcription.Transcript:
        heard.append((note.audio, note.raw))
        return transcription.Transcript(text="quiero cancelar mi turno", language="es", audio_ms=1800, vendor="fake")

    def no_ears(asked: object, catalog: object, keys: object) -> None:
        return None

    monkeypatch.setattr(providers, "ears_for", no_ears)
    monkeypatch.setattr(providers, "transcribe", transcribe)
    note: dict[str, object] = {"from": "59899000001", "id": "wamid.5", "type": "audio", "audio": {"id": "media.7"}}
    (message,) = webhook.messages_in(a_body(note))
    async with httpx.AsyncClient(transport=httpx.MockTransport(meta.answer)) as http:
        assert await whatsapp.take_up(side.parts, a_thread(side, http, message, agents_line=True), message) is None
    assert heard == [(b"OggS", False)]
    assert asked == ["quiero cancelar mi turno"]
    assert meta.read == [("wamid.5", True)]


@needs_the_database
async def test_a_voice_note_that_cannot_be_fetched_is_read_and_nothing_is_asked(side: Side, asked: list[str]) -> None:
    """Meta keeps no such audio: the message is marked read with no typing promised, and the model is not asked."""
    meta = Graph(refusal=(400, "Unsupported get request. Object with ID 'media.9' does not exist"))
    note: dict[str, object] = {"from": "59899000001", "id": "wamid.6", "type": "audio", "audio": {"id": "media.9"}}
    (message,) = webhook.messages_in(a_body(note))
    async with httpx.AsyncClient(transport=httpx.MockTransport(meta.answer)) as http:
        assert await whatsapp.take_up(side.parts, a_thread(side, http, message, agents_line=True), message) is None
    assert asked == []


# ── whose number a signed body reaches ──


@needs_the_database
async def test_a_body_an_orgs_app_signed_never_reaches_a_number_of_another_org(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, caplog: pytest.LogCaptureFixture
) -> None:
    """An org signs, with its own app's secret, a body that names another org's number as the one written to."""
    number = f"+5982{secrets.randbelow(10**7):07d}"
    route = RouteToWrite(
        org=tenant.org, number=number, agent="recepcion", channel=Channel.whatsapp, env=Env.sandbox, account="1055"
    )
    async with sessions.begin() as session:
        own = WhatsappNumber(org=tenant.org, phone_number_id="1055", access_token="a token", app_secret="theirs")
        await accounts.put_carrier(session, side.parts.vault, own)
        await RouteRepository(session).put(route)
    (message,) = webhook.messages_in(a_body(a_text("hola")))
    forged = dataclasses.replace(message, number=number, signed_for=frozenset({"another org"}))
    assert await side.threads.receive(forged) is True
    assert "the Meta app that signed it is not that number's" in caplog.text
    # The same message, vouched for by the number's own org, is read: nobody holds the agent, so it waits.
    theirs = dataclasses.replace(forged, signed_for=frozenset({tenant.org}))
    assert await side.threads.receive(theirs) is True
    assert "nobody holds agent recepcion" in caplog.text


# ── where a message of the agent's stands ──


class Writing:
    """A call's writing, as a receipt needs it: what was queued for its log."""

    def __init__(self) -> None:
        """Nothing written yet."""
        self.written: list[tuple[str, object]] = []

    def write(self, kind: str, event: object) -> None:
        """Keep the entry that would be queued."""
        self.written.append((kind, event))


@needs_the_database
async def test_a_receipt_is_said_on_the_contacts_open_conversation_and_on_no_other(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Meta says a reply was read: the conversation's log says so; a receipt another org's app signed says nothing."""
    number = f"+5982{secrets.randbelow(10**7):07d}"
    route = RouteToWrite(
        org=tenant.org, number=number, agent="recepcion", channel=Channel.whatsapp, env=Env.sandbox, account="1055"
    )
    async with sessions.begin() as session:
        own = WhatsappNumber(org=tenant.org, phone_number_id="1055", access_token="a token", app_secret="theirs")
        await accounts.put_carrier(session, side.parts.vault, own)
        await RouteRepository(session).put(route)
    writing = Writing()
    running = cast("Session", SimpleNamespace(call=SimpleNamespace(writing=writing)))
    (message,) = webhook.messages_in(a_body(a_text("hola")))
    async with httpx.AsyncClient(transport=httpx.MockTransport(Graph().answer)) as http:
        thread = OpenThread(session=running, inbound=message, reaches=ByWhatsapp(http, "t", Ears(side.parts, SCOPE)))
        side.threads._open[ThreadKey(tenant.org, Env.sandbox, number, "59899000001")] = thread
        read = Receipt(number, "1055", "59899000001", "wamid.out.1", "read", signed_for=frozenset({tenant.org}))
        await side.threads.note(read)
        await side.threads.note(dataclasses.replace(read, signed_for=frozenset({"another org"})))
        await side.threads.note(dataclasses.replace(read, wa_id="59899000002"))
    assert writing.written == [
        ("message.status", MessageStatus(message_id="wamid.out.1", status="read", to="+59899000001", error=None))
    ]


# ── a conversation by SMS ──


@needs_the_database
async def test_a_message_by_sms_is_answered_from_the_number_written_to_and_marks_nothing_read(
    side: Side, asked: list[str]
) -> None:
    """An SMS has no read mark and no typing sign: the message is taken up, and the reply goes out through Twilio."""
    twilio = Twilio()
    message = sms.read_message(
        {"To": "+15550100000", "From": "+59899000001", "Body": "hola", "MessageSid": "SM1", "AccountSid": "AC1"}
    )
    assert (message.channel, message.caller, message.text) == (Channel.sms, "+59899000001", "hola")
    async with httpx.AsyncClient(transport=twilio.transport()) as http:
        account = TwilioAccount(twilio.account_sid, twilio.user, twilio.secret)
        by_sms = BySms(http, account, "https://box.example/v1/sms/twilio/a-mark/status")
        running = cast("Session", SimpleNamespace(line=SimpleNamespace(agent_may_speak=True)))
        thread = OpenThread(session=running, inbound=message, reaches=by_sms)
        assert await whatsapp.take_up(side.parts, thread, message) is None
        await by_sms.send(message, "¡Hola! " + "palabra " * 300)
    assert asked == ["hola"]
    assert [(sent["From"], sent["To"]) for sent in twilio.messages] == [("+15550100000", "+59899000001")] * 2
    assert all(len(sent["Body"]) <= texts.LONGEST for sent in twilio.messages)
    assert twilio.messages[0]["StatusCallback"].endswith("/status")


def test_a_whatsapp_threads_name_is_as_it_was_and_an_sms_threads_says_its_channel() -> None:
    """Two gateways of two releases agree on a WhatsApp thread; the same contact by SMS is another thread."""
    on_whatsapp = ThreadKey("org_1", Env.sandbox, "+15550100000", "59899000001")
    by_sms = ThreadKey("org_1", Env.sandbox, "+15550100000", "59899000001", Channel.sms)
    assert str(on_whatsapp) == "org_1|sandbox|+15550100000|59899000001"
    assert str(by_sms) == "org_1|sandbox|+15550100000|59899000001|sms"


@needs_the_database
@pytest.mark.parametrize(("kind", "account"), [("page", "1472943555898656"), ("instagram", "17841400000000001")])
async def test_a_message_on_messenger_or_instagram_is_seen_read_and_answered_from_the_page(
    side: Side, asked: list[str], kind: str, account: str
) -> None:
    """Seen, "typing…" while the model writes, the words read, and the reply sent from the Page to Meta's id of them."""
    page = "1472943555898656"
    event = {"sender": {"id": "7001"}, "recipient": {"id": account}, "message": {"mid": "m_1", "text": "hola"}}
    body = json.dumps({"object": kind, "entry": [{"id": account, "messaging": [event]}]}).encode()
    (message,) = messaging.messaging_in(body, {account: page}).messages
    seen: list[tuple[str, object]] = []

    def meta(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        seen.append((request.url.path, sent.get("sender_action") or sent["message"]["text"]))
        return httpx.Response(200, json={"recipient_id": "7001", "message_id": "m_2"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(meta)) as http:
        by_messenger = ByMessenger(http, "a page token", Ears(side.parts, SCOPE))
        running = cast("Session", SimpleNamespace(line=SimpleNamespace(agent_may_speak=True)))
        thread = OpenThread(session=running, inbound=message, reaches=by_messenger)
        assert await whatsapp.take_up(side.parts, thread, message) is None
        await by_messenger.send(message, "¡Hola! ¿En qué te ayudo?")
    assert asked == ["hola"]
    assert seen == [
        (f"/v21.0/{page}/messages", "mark_seen"),
        (f"/v21.0/{page}/messages", "typing_on"),
        (f"/v21.0/{page}/messages", "¡Hola! ¿En qué te ayudo?"),
    ]
    assert message.caller == f"{'messenger' if kind == 'page' else 'instagram'}:7001"
