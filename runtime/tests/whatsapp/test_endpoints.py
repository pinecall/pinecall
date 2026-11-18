"""Meta's webhook over HTTP: an org's own app subscribes with the word it was given, and its signed bodies are taken."""

import os
import secrets

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.kit.crypto import Vault
from runtime.telephony.service import accounts
from runtime.telephony.service.whatsapp_number import WhatsappNumber
from tests.conftest import Gateway, Tenant, needs_the_services
from tests.fakes.meta import a_body, a_text, signed

THEIRS = "the secret of the org's own Meta app"


@needs_the_services
async def test_an_org_is_told_what_to_type_in_its_meta_app_and_meta_subscribes_with_it(
    gateway: Gateway, tenant: Tenant
) -> None:
    """The callback URL and the verify token an org reads are the ones Meta's handshake is answered for."""
    told = await gateway.http.get("/v1/whatsapp/subscription", headers=tenant.person)
    assert told.status_code == 200, told.text
    subscription = told.json()
    assert subscription["callback_url"].endswith("/v1/whatsapp/webhook")
    assert subscription["field"] == "messages"
    asked = {"hub.mode": "subscribe", "hub.verify_token": subscription["verify_token"], "hub.challenge": "1158201444"}
    answered = await gateway.http.get("/v1/whatsapp/webhook", params=asked)
    assert (answered.status_code, answered.text) == (200, "1158201444")
    refused = await gateway.http.get("/v1/whatsapp/webhook", params={**asked, "hub.verify_token": "a guess"})
    assert refused.status_code == 403


@needs_the_services
async def test_a_body_an_orgs_own_app_signed_is_taken_and_a_strangers_is_refused(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The secret an org brought with its number is the one its deliveries are checked against."""
    number = f"10{secrets.randbelow(10**10)}"
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    async with sessions.begin() as session:
        brought = WhatsappNumber(org=tenant.org, phone_number_id=number, access_token="a token", app_secret=THEIRS)
        await accounts.put_carrier(session, vault, brought)
    body = a_body(a_text("hola"), phone_number_id=number)
    headers = {"content-type": "application/json"}
    taken = await gateway.http.post(
        "/v1/whatsapp/webhook", content=body, headers={**headers, "x-hub-signature-256": signed(body, THEIRS)}
    )
    assert (taken.status_code, taken.json()) == (200, {"received": 1})
    for signature in (signed(body, "a stranger's secret"), signed(body)):
        refused = await gateway.http.post(
            "/v1/whatsapp/webhook", content=body, headers={**headers, "x-hub-signature-256": signature}
        )
        assert refused.status_code == 403, refused.text
