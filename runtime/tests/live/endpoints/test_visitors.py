"""A page's tokens: seated with the attributes it asked for and its contact, and reading its log as itself."""

import asyncio
import json
import os
import secrets
import time

import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.compliance.service import dial_guards
from runtime.compliance.service.dial_guards import Guards
from runtime.enums import Channel, Env
from runtime.kit.crypto import Vault
from runtime.kit.text import JsonObject
from runtime.telephony.repository import RouteRepository, RouteToWrite
from runtime.telephony.service import accounts
from runtime.telephony.service.twilio_carrier import TwilioCarrier
from runtime.wire.dispatch import Dispatch
from tests.conftest import Gateway, Tenant, holding, needs_the_services
from tests.fakes.twilio import Twilio


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
