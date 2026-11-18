"""Whose Meta token speaks for a WhatsApp number: the org's own account's, else the box's Meta app."""

import os
import secrets

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.kit.crypto import Vault
from runtime.platform import service as platform
from runtime.postgres import BoxSession
from runtime.providers.service import credentials
from runtime.telephony.service import accounts
from runtime.telephony.service.whatsapp_number import WhatsappNumber
from runtime.whatsapp.service.webhook import BOX_ACCOUNT
from tests.conftest import Tenant, make_tenant, needs_the_database

# The box's Meta app is sealed as providers seals a vendor's key; `drop_box_key` refuses a name that
# is no vendor of a call, so the test forgets its row by its name.
META_APP_ROW: platform.Setting[None] = platform.Setting(f"credentials/{BOX_ACCOUNT}", lambda _: None, lambda _: {})


@needs_the_database
async def test_the_orgs_own_meta_token_answers_and_an_org_without_one_answers_on_the_boxs(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The org's own WhatsApp account speaks with its token; any other org with the box's app."""
    other = await make_tenant(sessions)
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    number = f"10{secrets.randbelow(10**10)}"
    app = {"app_secret": "s", "verify_token": "w", "access_token": "the box's"}
    async with sessions.begin() as session:
        await credentials.put_box_credentials(BoxSession(session), vault, BOX_ACCOUNT, app)
        at_meta = WhatsappNumber(org=tenant.org, phone_number_id=number, access_token="the org's")
        await accounts.put_carrier(session, vault, at_meta)
    # The box's app is every test's database: left behind, it opens the door the others find closed.
    try:
        async with sessions() as session:
            assert await accounts.meta_token_for(session, vault, tenant.org, number) == "the org's"
            assert await accounts.meta_token_for(session, vault, other.org, number) == "the box's"
    finally:
        async with sessions.begin() as session:
            await platform.delete_setting(BoxSession(session), META_APP_ROW)


@needs_the_database
async def test_the_apps_that_sign_for_a_number_are_the_ones_brought_with_a_secret(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Meta's webhook asks by the number alone: every org that brought it with its own app's secret, and no other."""
    other = await make_tenant(sessions)
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    theirs, the_boxs = (f"10{secrets.randbelow(10**10)}" for _ in range(2))
    async with sessions.begin() as session:
        for org in (tenant.org, other.org):
            own = WhatsappNumber(org=org, phone_number_id=theirs, access_token="t", app_secret=f"secret of {org}")
            await accounts.put_carrier(session, vault, own)
        on_the_boxs_app = WhatsappNumber(org=tenant.org, phone_number_id=the_boxs, access_token="t")
        await accounts.put_carrier(session, vault, on_the_boxs_app)
    async with sessions() as session:
        apps = await accounts.list_own_meta_apps(session, vault, {theirs, the_boxs})
        assert {(app.org, app.phone_number_id, app.app_secret) for app in apps} == {
            (tenant.org, theirs, f"secret of {tenant.org}"),
            (other.org, theirs, f"secret of {other.org}"),
        }
        assert await accounts.list_own_meta_apps(session, vault, {"a number nobody brought"}) == []


@needs_the_database
async def test_a_number_brought_again_with_a_new_token_keeps_its_apps_secret(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A token is renewed with no secret typed: the app's secret stays; one typed replaces it."""
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    number = f"10{secrets.randbelow(10**10)}"

    async def bring(token: str, secret: str = "") -> WhatsappNumber:
        async with sessions.begin() as session:
            brought = WhatsappNumber(org=tenant.org, phone_number_id=number, access_token=token, app_secret=secret)
            kept = await accounts.put_carrier(session, vault, brought)
        assert isinstance(kept, WhatsappNumber)
        return kept

    assert (await bring("first", "the secret")).app_secret == "the secret"
    renewed = await bring("second")
    assert (renewed.access_token, renewed.app_secret) == ("second", "the secret")
    assert (await bring("third", "another secret")).app_secret == "another secret"
