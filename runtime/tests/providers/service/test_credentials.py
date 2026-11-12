"""An org's copy of the box's key follows it: rotated or dropped, the copy goes along; a key the org brought stays."""

import os
import secrets

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.enums import Stage
from runtime.kit.crypto import Vault
from runtime.postgres import BoxSession
from runtime.providers.service import credentials, plugins
from tests.conftest import make_tenant


# A vendor of this test alone: the box's acme key is every other test's.
async def _keyed(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> tuple[str, Vault, str, str]:
    vendor, vault = f"rotated-{secrets.token_hex(4)}", Vault(os.environ["PINECALL_VAULT_KEY"])
    monkeypatch.setitem(plugins.list_vendors(), vendor, plugins.Vendor(vendor, frozenset(Stage)))
    copying, bringing = await make_tenant(sessions), await make_tenant(sessions)
    async with sessions.begin() as session:
        await credentials.put_box_credentials(BoxSession(session), vault, vendor, "the-old-key")
        await credentials.put_own_credentials(session, vault, copying.org, vendor, "the-old-key")
        await credentials.put_own_credentials(session, vault, bringing.org, vendor, "their-own-key")
    return vendor, vault, copying.org, bringing.org


async def test_a_rotated_box_key_takes_an_orgs_copy_of_it_along_and_leaves_a_key_the_org_brought(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    vendor, vault, copying, bringing = await _keyed(sessions, monkeypatch)
    async with sessions.begin() as session:
        await credentials.put_box_credentials(BoxSession(session), vault, vendor, "the-new-key")
    async with sessions.begin() as session:
        assert (await credentials.box_credentials(session, vault))[vendor] == "the-new-key"
        assert (await credentials.own_credentials(session, vault, copying))[vendor] == "the-new-key"
        assert (await credentials.own_credentials(session, vault, bringing))[vendor] == "their-own-key"
        await credentials.drop_box_key(BoxSession(session), vault, vendor)


async def test_a_dropped_box_key_takes_an_orgs_copy_of_it_along_and_leaves_a_key_the_org_brought(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    vendor, vault, copying, bringing = await _keyed(sessions, monkeypatch)
    async with sessions.begin() as session:
        await credentials.drop_box_key(BoxSession(session), vault, vendor)
    async with sessions.begin() as session:
        assert vendor not in await credentials.box_credentials(session, vault)
        assert vendor not in await credentials.own_credentials(session, vault, copying)
        assert (await credentials.own_credentials(session, vault, bringing))[vendor] == "their-own-key"
