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
from runtime.whatsapp.service import BOX_ACCOUNT
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
