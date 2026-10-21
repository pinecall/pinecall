"""An org's copy of the box's key follows it: rotated or dropped, the copy goes along; a key the org brought stays."""

import os
import secrets

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.providers.service import held
from tests.conftest import make_tenant


# A vendor of this test alone: the box's acme key is every other test's.
async def _keyed(sessions: async_sessionmaker[AsyncSession]) -> tuple[str, Vault, str, str]:
    vendor, vault = f"rotated-{secrets.token_hex(4)}", Vault(os.environ["PINECALL_VAULT_KEY"])
    copying, bringing = await make_tenant(sessions), await make_tenant(sessions)
    async with sessions.begin() as session:
        await held.put_box_credentials(session, vault, vendor, "the-old-key")
        await held.put_own_credentials(session, vault, copying.org, vendor, "the-old-key")
        await held.put_own_credentials(session, vault, bringing.org, vendor, "their-own-key")
    return vendor, vault, copying.org, bringing.org


async def test_a_rotated_box_key_takes_an_orgs_copy_of_it_along_and_leaves_a_key_the_org_brought(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    vendor, vault, copying, bringing = await _keyed(sessions)
    async with sessions.begin() as session:
        await held.put_box_credentials(session, vault, vendor, "the-new-key")
    async with sessions.begin() as session:
        assert (await held.box_credentials(session, vault))[vendor] == "the-new-key"
        assert (await held.own_credentials(session, vault, copying))[vendor] == "the-new-key"
        assert (await held.own_credentials(session, vault, bringing))[vendor] == "their-own-key"
        await held.drop_box_credentials(session, vault, vendor)


async def test_a_dropped_box_key_takes_an_orgs_copy_of_it_along_and_leaves_a_key_the_org_brought(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    vendor, vault, copying, bringing = await _keyed(sessions)
    async with sessions.begin() as session:
        assert await held.drop_box_credentials(session, vault, vendor)
    async with sessions.begin() as session:
        assert vendor not in await held.box_credentials(session, vault)
        assert vendor not in await held.own_credentials(session, vault, copying)
        assert (await held.own_credentials(session, vault, bringing))[vendor] == "their-own-key"
