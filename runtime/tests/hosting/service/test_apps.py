"""What the box hosts for an org: an app, the token its process runs on, what serves it and what failed."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service import keys
from runtime.accounts.service.key_cache import KeyCache
from runtime.accounts.service.keys import KeyDetails
from runtime.enums import Env
from runtime.exceptions import NotFound
from runtime.hosting.models import HostedApp
from runtime.hosting.repository import HostedAppRepository
from runtime.hosting.service.apps import (
    App,
    agents_of,
    delete_app,
    environment_for,
    list_standing,
    open_app,
    start_app,
)
from runtime.hosting.service.hostnames import host_of
from runtime.hosting.service.releases import check_source, keep_release, list_releases
from runtime.kit.crypto import fingerprint
from runtime.signal import LocalSignal
from tests.conftest import Tenant, needs_the_database
from tests.hosting.factories import PROJECT, VAULT, opened

pytestmark = needs_the_database

LABEL = "hosted app support"


async def hosted_keys(sessions: async_sessionmaker[AsyncSession], org: str) -> list[KeyDetails]:
    """The keys minted for the org's hosted app, oldest first."""
    async with sessions() as session:
        return [key for key in await keys.list_keys(session, org) if key.label == LABEL]


async def token_of(session: AsyncSession, app: App) -> str:
    """The token the app's process is started with."""
    return (await environment_for(session, VAULT, None, app))["PINECALL_KEY"]


async def row_of(session: AsyncSession, org: str) -> HostedApp:
    """The org's one hosted app, as its row holds it."""
    return (await session.execute(select(HostedApp).where(HostedApp.org == org))).scalar_one()


async def test_an_app_opened_is_hosted_on_a_live_server_token_kept_sealed(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, key_cache: KeyCache
) -> None:
    """Its token is minted for the env, sealed in the row, and opens the gateway; opened twice, one token lives."""
    app = App(org=tenant.org, env=Env.sandbox, name="support")
    async with sessions() as session:
        assert await list_standing(session, Env.sandbox, tenant.org) == []
    await opened(sessions, key_cache, app)
    async with sessions.begin() as session:
        await open_app(session, VAULT, key_cache, app, created_by="m_ben")
    async with sessions() as session:
        (listed,) = await list_standing(session, Env.sandbox, tenant.org)
        row = await row_of(session, tenant.org)
        token = await token_of(session, app)
        with pytest.raises(NotFound, match="hosts no app called nobody"):
            await token_of(session, App(org=tenant.org, env=Env.sandbox, name="nobody"))
    assert await key_cache.verify(token) is not None
    assert (listed.name, listed.release, listed.created_by) == ("support", None, "m_ana")
    assert token.startswith("pc_test_")
    assert VAULT.open(row.sealed_key) == token
    assert row.key_fingerprint == fingerprint(token)
    minted = await hosted_keys(sessions, tenant.org)
    assert [(key.env, key.revoked_at is None) for key in minted] == [(Env.sandbox, True), (Env.sandbox, False)]


async def test_a_host_reported_failed_is_news_once_the_serving_one_serves_no_more_and_a_start_forgives(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, key_cache: KeyCache
) -> None:
    app = App(org=tenant.org, env=Env.sandbox, name="support")
    await opened(sessions, key_cache, app, "first", "second")
    first = host_of(app.org, app.env, app.name, 1, "a" * 64, "")
    second = host_of(app.org, app.env, app.name, 2, "b" * 64, "")
    where = (app.org, app.env, app.name)
    async with sessions.begin() as session:
        marks = HostedAppRepository(session)
        await marks.mark_live(*where, release=1, host=first, runner="runner-sandbox")
        # The next release's host failing is news once; the host serving goes on serving.
        assert await marks.mark_failed(*where, host=second, why="secrets: 403", runner="runner-sandbox")
        assert not await marks.mark_failed(*where, host=second, why="secrets: 403", runner="runner-sandbox")
        row = await row_of(session, tenant.org)
        await session.refresh(row)
        assert (row.failed_host, row.failed_why, row.live_host, row.live_release) == (second, "secrets: 403", first, 1)
        # The host that served, given up on, is news again and serves no more; a person's start forgives it.
        assert await marks.mark_failed(*where, host=first, why="exited again", runner="runner-sandbox")
        await session.refresh(row)
        assert (row.live_host, row.live_release, row.failed_host) == (None, None, first)
        await start_app(session, LocalSignal(), app)
        await session.refresh(row)
    assert (row.failed_host, row.failed_why, row.stopped_at) == (None, "", None)


async def test_a_release_gone_live_serves_the_app_until_the_next_one_does(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, key_cache: KeyCache
) -> None:
    """A newer release is wanted while the live host keeps serving."""
    app = App(org=tenant.org, env=Env.production, name="support")
    await opened(sessions, key_cache, app, "")
    async with sessions.begin() as session:
        (wanted,) = await list_standing(session, Env.production, tenant.org)
        assert wanted.host is not None
        await HostedAppRepository(session).mark_live(
            app.org, app.env, app.name, release=1, host=wanted.host, runner="apps-1"
        )
        await keep_release(session, app, check_source(PROJECT), author="m_ana", note="")
    async with sessions() as session:
        (newer,) = await list_standing(session, Env.production, tenant.org)
    assert (newer.release, newer.live_host, newer.live_release) == (2, wanted.host, 1)


async def test_deleting_an_app_takes_its_releases_and_revokes_its_token(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, key_cache: KeyCache
) -> None:
    """Gone: no row, no release, and its token opens nothing."""
    app = App(org=tenant.org, env=Env.production, name="support")
    await opened(sessions, key_cache, app, "")
    async with sessions() as session:
        token = await token_of(session, app)
    assert await key_cache.verify(token) is not None
    async with sessions.begin() as session:
        await delete_app(session, key_cache, LocalSignal(), app)
    async with sessions.begin() as session:
        assert await list_standing(session, Env.production, tenant.org) == []
        with pytest.raises(NotFound):
            await list_releases(session, None, app)
        with pytest.raises(NotFound, match="hosts no app called support"):
            await delete_app(session, key_cache, LocalSignal(), app)
    assert await key_cache.verify(token) is None
    (minted,) = await hosted_keys(sessions, tenant.org)
    assert minted.revoked_at is not None


def test_an_apps_agents_are_what_the_processes_of_its_name_hold_and_nobody_elses() -> None:
    holding = {
        "brightside-r4-7247b145": ["clinic-front-desk", "clinic-billing"],
        "brightside-r4-f438d14a": ["clinic-billing", "clinic-front-desk"],
        "brightside-dental-r2-0a1b2c3d": ["dental-desk"],
        "anas-macbook.local": ["clinic-front-desk", "drafts"],
    }
    assert agents_of("brightside", holding) == ["clinic-billing", "clinic-front-desk"]
    assert agents_of("brightside-dental", holding) == ["dental-desk"]
    assert agents_of("support", holding) == []
