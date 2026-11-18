"""A contact who stops the messages: the word honoured before the model reads it, and what they are told."""

import asyncio
import secrets
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents.declaration import STOP_MESSAGES
from runtime.compliance.service import consents, keywords, policy
from runtime.enums import Channel, Env
from runtime.live.peers import THREADS, ThreadKey
from runtime.live.service import opt_outs
from runtime.live.service.opt_outs import Stop
from runtime.live.service.replies import BySms
from runtime.live.service.whatsapp import OpenThread
from runtime.telephony.models import Route
from runtime.telephony.repository import RouteRepository, RouteToWrite
from runtime.telephony.service import accounts, sms
from runtime.telephony.service.twilio import TwilioAccount
from runtime.telephony.service.twilio_carrier import TwilioCarrier
from runtime.whatsapp.service.webhook import Inbound
from tests.calls.factories import CALL, entry
from tests.conftest import Tenant, needs_the_database
from tests.fakes.twilio import Twilio
from tests.live.conftest import Side

if TYPE_CHECKING:
    from runtime.session.session import Session

CONTACT = "+59899000001"


def a_text(number: str, body: str, **more: str) -> Inbound:
    """One SMS as Twilio posts it, from the contact to the number."""
    posted = {"To": number, "From": CONTACT, "Body": body, "MessageSid": f"SM{secrets.token_hex(4)}", **more}
    return sms.read_message(posted)


@pytest.fixture
async def routed(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> tuple[Twilio, str]:
    """A number of the org's Twilio account that answers SMS in the sandbox; the fake account and the number."""
    twilio, number = Twilio(), f"+1555{secrets.randbelow(10**7):07d}"
    # The side's own client answers 404 to everything: for these tests it is the fake account.
    monkeypatch.setattr(side.parts.http, "_transport", twilio.transport())
    account = TwilioCarrier(org=tenant.org, account_sid=twilio.account_sid, user=twilio.user, secret=twilio.secret)
    route = RouteToWrite(
        org=tenant.org, number=number, agent="riley", channel=Channel.sms, env=Env.sandbox, account=twilio.account_sid
    )
    async with sessions.begin() as session:
        await accounts.put_carrier(session, side.parts.vault, account)
        await RouteRepository(session).put(route)
    return twilio, number


async def the_route(sessions: async_sessionmaker[AsyncSession], org: str, number: str) -> Route:
    """The org's SMS route at the number."""
    async with sessions() as session:
        found = await RouteRepository(session).find(org, number, Channel.sms)
    assert found is not None
    return found.route


@needs_the_database
async def test_a_text_that_says_stop_is_honoured_before_the_model_reads_it_and_start_lifts_it(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, routed: tuple[Twilio, str]
) -> None:
    """STOP puts the contact on the list and is answered by nobody here: the carrier confirms it. START lifts it."""
    twilio, number = routed
    route = await the_route(sessions, tenant.org, number)
    scope = Scope(tenant.org, Env.sandbox)
    assert await opt_outs.take_word(side.parts, route, a_text(number, "hola"), None) is None
    assert await opt_outs.take_word(side.parts, route, a_text(number, "Stop."), "call_1") == "stop"
    async with sessions() as session:
        history = await consents.history_of(session, scope, CONTACT)
    assert (history.standing, history.rows[0].source, history.rows[0].text, history.rows[0].call) == (
        "opted_out",
        keywords.TEXTED_STOP,
        "Stop.",
        "call_1",
    )
    assert await opt_outs.refuses_messages(side.parts, scope, CONTACT)
    # Whatever they write next is not answered, until the word that starts the messages again.
    assert await opt_outs.take_word(side.parts, route, a_text(number, "are you there?"), None) == "silenced"
    assert await opt_outs.take_word(side.parts, route, a_text(number, "START"), None) == "start"
    assert not await opt_outs.refuses_messages(side.parts, scope, CONTACT)
    assert await opt_outs.take_word(side.parts, route, a_text(number, "yes"), None) is None
    assert twilio.messages == []


# On 2026-11-18 a real STOP landed on the gateway that did not hold the contact's thread: the number went on
# the list, and the conversation stayed open for its two idle hours on the other gateway.
@needs_the_database
async def test_a_stop_word_is_answered_by_the_gateway_that_holds_the_contacts_thread(
    side: Side, tenant: Tenant, routed: tuple[Twilio, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Landing where the thread is not held, the word is handed on whole; handed here, it is honoured here."""
    _twilio, number = routed
    scope, stop = Scope(tenant.org, Env.sandbox), a_text(number, "STOP", OptOutType="STOP")
    key = ThreadKey(tenant.org, Env.sandbox, number, stop.wa_id, Channel.sms)
    heard = await THREADS.subscribe(side.parts.signal, gateway="the-other-gateway")

    def held_elsewhere(asked: ThreadKey) -> str | None:
        return "the-other-gateway" if asked == key else None

    with monkeypatch.context() as patched:
        patched.setattr(side.parts.owners, "find_thread_holder", held_elsewhere)
        try:
            assert await side.threads.receive(stop)
            handed = THREADS.load(await asyncio.wait_for(anext(heard), 2))
        finally:
            heard.close()
    assert (handed.text, handed.channel, handed.carrier_replied) == ("STOP", Channel.sms, True)
    assert not await opt_outs.refuses_messages(side.parts, scope, CONTACT), "the holder writes it, with its call"
    # The same message, handed to this gateway by another: nobody holds the thread any more, so it is honoured here.
    handed_here = THREADS.name.format(gateway=side.parts.owners.id)
    deadline = time.monotonic() + 5
    while not await opt_outs.refuses_messages(side.parts, scope, CONTACT):
        assert time.monotonic() < deadline, "the word handed on was never honoured"
        side.parts.signal.publish(handed_here, THREADS.dump(handed))
        await asyncio.sleep(0.05)


@needs_the_database
async def test_an_org_that_wrote_its_own_sentences_says_them_unless_the_carrier_already_answered(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, routed: tuple[Twilio, str]
) -> None:
    """The org's confirmation and its HELP answer go out from the number; a word the carrier took is left to it."""
    twilio, number = routed
    route = await the_route(sessions, tenant.org, number)
    said = policy.Policy(
        sms_stop_reply="Clinica: no more messages.", sms_help_reply="Clinica: call 555.", sms_stop_words=("baja",)
    )
    async with sessions.begin() as session:
        await policy.put_policy(session, tenant.org, said, by="a person")
    assert await opt_outs.take_word(side.parts, route, a_text(number, "help"), None) == "help"
    assert await opt_outs.take_word(side.parts, route, a_text(number, "BAJA", OptOutType="STOP"), None) == "stop"
    assert [sent["Body"] for sent in twilio.messages] == ["Clinica: call 555."]
    assert await opt_outs.take_word(side.parts, route, a_text(number, "start"), None) == "start"
    assert await opt_outs.take_word(side.parts, route, a_text(number, "baja"), None) == "stop"
    assert [sent["Body"] for sent in twilio.messages] == ["Clinica: call 555.", "Clinica: no more messages."]


def a_thread(twilio: Twilio, http: httpx.AsyncClient, number: str, written: list[tuple[str, object]]) -> OpenThread:
    """An open SMS conversation whose call keeps what is written on it."""

    def write(kind: str, event: object) -> None:
        written.append((kind, event))

    writing = SimpleNamespace(write=write)
    running = cast("Session", SimpleNamespace(call=SimpleNamespace(writing=writing)))
    account = TwilioAccount(twilio.account_sid, twilio.user, twilio.secret)
    return OpenThread(session=running, inbound=a_text(number, "hola"), reaches=BySms(http, account, "https://x/status"))


async def test_a_thread_whose_contact_stopped_is_sent_nothing_more_and_ends() -> None:
    """The model's tool, or the list, silences the thread: what the agent writes after is not sent."""
    twilio = Twilio()
    written: list[tuple[str, object]] = []
    async with httpx.AsyncClient(transport=twilio.transport()) as http:
        thread = a_thread(twilio, http, "+15550100000", written)
        await thread.reply(entry(1, "turn.agent", {"text": "Hola, ¿en qué te ayudo?"}))
        await thread.reply(entry(2, "tool.call", {"call_id": "c1", "name": STOP_MESSAGES, "arguments": {}}))
        await thread.reply(entry(3, "turn.agent", {"text": "Listo, no te escribo más."}))
        assert thread.stopped
        assert thread.heard.get_nowait() == Stop(by="agent", written=False, call=CALL)
        # The list says so too, on a thread no tool stopped.
        listed = a_thread(twilio, http, "+15550100000", written)

        async def on_the_list() -> bool:
            return True

        listed.refuses = on_the_list
        await listed.reply(entry(4, "turn.agent", {"text": "¿Sigues ahí?"}))
    assert [sent["Body"] for sent in twilio.messages] == ["Hola, ¿en qué te ayudo?"]


@needs_the_database
async def test_a_contact_the_agent_took_off_is_told_once_in_the_platforms_words_or_the_orgs(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The carrier saw no word of its own and confirmed nothing: the one confirmation is sent from here."""
    twilio, scope = Twilio(), Scope(tenant.org, Env.sandbox)
    async with httpx.AsyncClient(transport=twilio.transport()) as http:
        thread = a_thread(twilio, http, "+15550100000", [])
        stop = Stop(by="agent", note="no more texts please", written=False, call="call_7")
        await opt_outs.take_off(side.parts, scope, thread.inbound, thread.reaches, stop)
        async with sessions.begin() as session:
            await policy.put_policy(session, tenant.org, policy.Policy(sms_stop_reply=""), by="a person")
        await opt_outs.take_off(side.parts, scope, thread.inbound, thread.reaches, Stop(by="agent"))
        # The contact's own word is the carrier's to confirm.
        await opt_outs.take_off(side.parts, scope, thread.inbound, thread.reaches, Stop(by="caller"))
    assert [sent["Body"] for sent in twilio.messages] == [keywords.TAKEN_OFF]
    async with sessions() as session:
        history = await consents.history_of(session, scope, CONTACT)
    assert [(row.source, row.text, row.call) for row in history.rows] == [
        (keywords.ASKED_THE_AGENT_IN_WRITING, "no more texts please", "call_7")
    ]
