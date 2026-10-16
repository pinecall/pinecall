"""What the box hosts for an org: an app, the token its process runs on, and its releases."""

import gzip
import io
import os
import tarfile

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.models import ApiKey
from pinecall_runtime.accounts.service import keys
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.hosting.models import HostedApp
from pinecall_runtime.hosting.service.apps import (
    LARGEST_SOURCE,
    App,
    checked_name,
    checked_source,
    delete_app,
    host_of,
    hosted_in,
    is_a_host_of,
    is_hosted,
    keep_release,
    key_of,
    list_apps,
    open_app,
    record_live,
    release_of,
    releases_of,
    source_of,
)
from pinecall_runtime.kit.crypto import Vault, fingerprint
from tests.conftest import Tenant, needs_the_database

VAULT = Vault(os.environ["PINECALL_VAULT_KEY"])
LABEL = "hosted app support"


def tarball(files: dict[str, bytes]) -> bytes:
    """A gzipped tarball of these files."""
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w:gz") as tar:
        for path, content in files.items():
            member = tarfile.TarInfo(path)
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))
    return packed.getvalue()


PROJECT = tarball({"package.json": b"{}", "agents/support/agent.ts": b"export default 1"})
APP = App(org="org_1", env=Env.production, name="support")


async def hosted_keys(sessions: async_sessionmaker[AsyncSession], org: str) -> list[ApiKey]:
    """The keys minted for the org's hosted app, oldest first."""
    async with sessions() as session:
        return [key for key in await keys.list_keys(session, org) if key.label == LABEL]


async def opened(sessions: async_sessionmaker[AsyncSession], app: App, *releases: str) -> None:
    """The app hosted, with a release per note given."""
    async with sessions.begin() as session:
        await open_app(session, VAULT, app, created_by="m_ana")
        for note in releases:
            await keep_release(session, app, checked_source(PROJECT), author="m_ana", note=note)


# ── an upload, checked before it is kept ──


def test_a_tarball_of_files_is_a_release_with_its_sha256() -> None:
    """The upload is kept as it came."""
    source = checked_source(PROJECT)
    assert (source.data, len(source.sha256)) == (PROJECT, 64)


@pytest.mark.parametrize(
    "upload",
    [b"", b"not a tarball", gzip.compress(b"gzip, no tar inside", mtime=0)],
    ids=["nothing", "words", "gzip-of-words"],
)
def test_anything_but_a_gzipped_tarball_is_refused(upload: bytes) -> None:
    """Only a gzipped tarball is a release."""
    with pytest.raises(ValidationError, match="gzipped tarball"):
        checked_source(upload)


@pytest.mark.parametrize("path", ["../outside.txt", "agents/../../outside.txt", "/etc/passwd"])
def test_a_path_that_leaves_the_project_is_refused(path: str) -> None:
    """Whoever unpacks a release later writes inside its folder alone."""
    with pytest.raises(ValidationError, match="leaves the project"):
        checked_source(tarball({path: b"x"}))


def test_a_link_is_refused() -> None:
    """A symlink to /etc/passwd is no file of a project."""
    link = tarfile.TarInfo("agents/link")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w:gz") as tar:
        tar.addfile(link)
    with pytest.raises(ValidationError, match="a link or a device"):
        checked_source(packed.getvalue())


def test_an_upload_too_big_packed_or_unpacked_is_refused() -> None:
    """Over 10 MB is refused before it is read; a small bomb that unpacks past 100 MB, as it unpacks."""
    with pytest.raises(ValidationError, match="10 MB at most"):
        checked_source(b"\0" * (LARGEST_SOURCE + 1))
    bomb = tarfile.TarInfo("zeros")
    bomb.size = 101 * 1024 * 1024
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w:gz") as tar:
        tar.addfile(bomb, io.BytesIO(b"\0" * bomb.size))
    with pytest.raises(ValidationError, match="unpacks to 100 MB"):
        checked_source(packed.getvalue())


# ── hosts ──


def test_a_host_names_the_app_the_release_and_a_stamp_and_fits_a_host_name() -> None:
    """Another org, env, release or set of secrets is another host; the longest still fits 63."""
    host = host_of(APP, 7, "a" * 64, "")
    assert host.startswith("support-r7-")
    assert len(host) == len("support-r7-") + 8
    others = {
        host_of(APP, 7, "a" * 64, "CRM_TOKEN@1.5"),
        host_of(APP, 8, "a" * 64, ""),
        host_of(App(org="org_2", env=Env.production, name="support"), 7, "a" * 64, ""),
        host_of(App(org="org_1", env=Env.sandbox, name="support"), 7, "a" * 64, ""),
    }
    assert host not in others
    assert len(others) == 4
    assert len(host_of(App(org="org_1", env=Env.production, name="x" * 40), 123456, "a" * 64, "")) <= 63
    assert (release_of(host), release_of("support-r7")) == (7, None)


def test_a_host_is_the_apps_whatever_its_release_and_never_a_longer_names() -> None:
    """support-rest's host is not support's."""
    assert is_a_host_of("support", host_of(APP, 3, "a" * 64, ""))
    rest = App(org="org_1", env=Env.production, name="support-rest")
    assert not is_a_host_of("support", host_of(rest, 3, "a" * 64, ""))
    assert not is_a_host_of("support", "support-r3")


def test_a_name_longer_than_a_host_can_carry_is_refused() -> None:
    """Forty characters of slug at most."""
    assert checked_name("x" * 40) == "x" * 40
    with pytest.raises(ValidationError, match="40 characters at most"):
        checked_name("x" * 41)


# ── apps and releases ──


@needs_the_database
async def test_an_app_opened_is_hosted_on_a_live_server_token_kept_sealed(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Its token is minted for the env, sealed in the row, and opens the gateway; opened twice, one token lives."""
    app = App(org=tenant.org, env=Env.sandbox, name="support")
    async with sessions() as session:
        assert not await is_hosted(session, app)
    await opened(sessions, app)
    async with sessions.begin() as session:
        await open_app(session, VAULT, app, created_by="m_ben")
    async with sessions() as session:
        (listed,) = await list_apps(session, tenant.org, Env.sandbox)
        row = (await session.execute(select(HostedApp).where(HostedApp.org == tenant.org))).scalar_one()
        token = await key_of(session, VAULT, app)
        assert await keys.verify_key(session, token) is not None
        with pytest.raises(NotFound, match="hosts no app called nobody"):
            await key_of(session, VAULT, App(org=tenant.org, env=Env.sandbox, name="nobody"))
    assert (listed.name, listed.release, listed.created_by) == ("support", None, "m_ana")
    assert token.startswith("pc_test_")
    assert VAULT.open(row.sealed_key) == token
    assert row.key_fingerprint == fingerprint(token)
    minted = await hosted_keys(sessions, tenant.org)
    assert [(key.env, key.revoked_at is None) for key in minted] == [(Env.sandbox, True), (Env.sandbox, False)]


@needs_the_database
async def test_releases_are_numbered_from_one_newest_first_and_ten_are_kept_beside_the_live_one(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Release 3 serves the app; twelve more later, the newest ten and release 3 are kept."""
    app = App(org=tenant.org, env=Env.production, name="support")
    await opened(sessions, app, "first", "")
    async with sessions() as session:
        kept = await releases_of(session, app)
        (listed,) = await list_apps(session, tenant.org, Env.production)
        assert (await source_of(session, app, 1)).data == PROJECT
    assert [(row.release, row.note) for row in kept] == [(2, ""), (1, "first")]
    assert (kept[0].sha256, kept[0].bytes, listed.release) == (checked_source(PROJECT).sha256, len(PROJECT), 2)
    source = checked_source(PROJECT)
    async with sessions.begin() as session:
        await keep_release(session, app, source, author="m_ana", note="")
        await record_live(session, app, host_of(app, 3, source.sha256, ""), runner="r_1")
        for _ in range(12):
            await keep_release(session, app, source, author="m_ana", note="")
    async with sessions() as session:
        assert [row.release for row in await releases_of(session, app)] == [*range(15, 5, -1), 3]


@needs_the_database
async def test_a_release_gone_live_serves_the_app_until_the_next_one_does(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A newer release is wanted while the live host keeps serving."""
    app = App(org=tenant.org, env=Env.production, name="support")
    await opened(sessions, app, "")
    async with sessions.begin() as session:
        (wanted,) = [item for item in await hosted_in(session, Env.production) if item.org == tenant.org]
        await record_live(session, app, wanted.host, runner="apps-1")
        await keep_release(session, app, checked_source(PROJECT), author="m_ana", note="")
    async with sessions() as session:
        (newer,) = [item for item in await hosted_in(session, Env.production) if item.org == tenant.org]
        (listed,) = await list_apps(session, tenant.org, Env.production)
    assert (newer.release, newer.live_host, listed.live_release) == (2, wanted.host, 1)


@needs_the_database
async def test_each_env_hosts_its_own_apps_and_one_not_hosted_has_nothing_to_keep_or_read(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The sandbox's app is not production's; an app nobody opened is not found by any verb."""
    await opened(sessions, App(org=tenant.org, env=Env.sandbox, name="support"))
    nobody = App(org=tenant.org, env=Env.production, name="support")
    async with sessions.begin() as session:
        assert await list_apps(session, tenant.org, Env.production) == []
        with pytest.raises(NotFound, match="hosts no app called support"):
            await keep_release(session, nobody, checked_source(PROJECT), author="m_ana", note="")
        with pytest.raises(NotFound, match="hosts no app called support"):
            await releases_of(session, nobody)
        with pytest.raises(NotFound, match="no release 3"):
            await source_of(session, nobody, 3)
        with pytest.raises(NotFound, match="hosts no app called support"):
            await delete_app(session, nobody)


@needs_the_database
async def test_deleting_an_app_takes_its_releases_and_revokes_its_token(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Gone: no row, no release, and its token opens nothing."""
    app = App(org=tenant.org, env=Env.production, name="support")
    await opened(sessions, app, "")
    async with sessions() as session:
        token = await key_of(session, VAULT, app)
    async with sessions.begin() as session:
        await delete_app(session, app)
    async with sessions() as session:
        assert await list_apps(session, tenant.org, Env.production) == []
        with pytest.raises(NotFound):
            await releases_of(session, app)
        assert await keys.verify_key(session, token) is None
    (minted,) = await hosted_keys(sessions, tenant.org)
    assert minted.revoked_at is not None
