"""A release: an upload checked before it is kept, numbered from one, the newest ten kept beside the live one."""

import gzip
import io
import tarfile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service.key_cache import KeyCache
from runtime.enums import Env
from runtime.exceptions import NotFound, ValidationError
from runtime.hosting.repository import HostedAppRepository
from runtime.hosting.service.apps import App, list_standing
from runtime.hosting.service.hostnames import host_of
from runtime.hosting.service.releases import (
    LARGEST_SOURCE,
    check_name,
    check_source,
    keep_release,
    list_releases,
    source_of,
)
from tests.conftest import Tenant, needs_the_database
from tests.hosting.factories import PROJECT, opened, tarball

# ── an upload, checked before it is kept ──


def test_a_tarball_of_files_is_a_release_with_its_sha256() -> None:
    """The upload is kept as it came."""
    source = check_source(PROJECT)
    assert (source.data, len(source.sha256)) == (PROJECT, 64)


@pytest.mark.parametrize(
    "upload",
    [b"", b"not a tarball", gzip.compress(b"gzip, no tar inside", mtime=0)],
    ids=["nothing", "words", "gzip-of-words"],
)
def test_anything_but_a_gzipped_tarball_is_refused(upload: bytes) -> None:
    """Only a gzipped tarball is a release."""
    with pytest.raises(ValidationError, match="gzipped tarball"):
        check_source(upload)


@pytest.mark.parametrize("path", ["../outside.txt", "agents/../../outside.txt", "/etc/passwd"])
def test_a_path_that_leaves_the_project_is_refused(path: str) -> None:
    """Whoever unpacks a release later writes inside its folder alone."""
    with pytest.raises(ValidationError, match="leaves the project"):
        check_source(tarball({path: b"x"}))


def test_a_link_is_refused() -> None:
    """A symlink to /etc/passwd is no file of a project."""
    link = tarfile.TarInfo("agents/link")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w:gz") as tar:
        tar.addfile(link)
    with pytest.raises(ValidationError, match="a link or a device"):
        check_source(packed.getvalue())


def test_an_upload_too_big_packed_or_unpacked_is_refused() -> None:
    """Over 10 MB is refused before it is read; a small bomb that unpacks past 100 MB, as it unpacks."""
    with pytest.raises(ValidationError, match="10 MB at most"):
        check_source(b"\0" * (LARGEST_SOURCE + 1))
    bomb = tarfile.TarInfo("zeros")
    bomb.size = 101 * 1024 * 1024
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w:gz") as tar:
        tar.addfile(bomb, io.BytesIO(b"\0" * bomb.size))
    with pytest.raises(ValidationError, match="unpacks to 100 MB"):
        check_source(packed.getvalue())


def test_a_name_longer_than_a_host_can_carry_is_refused() -> None:
    """Forty characters of slug at most."""
    assert check_name("x" * 40) == "x" * 40
    with pytest.raises(ValidationError, match="40 characters at most"):
        check_name("x" * 41)


# ── the releases of an app ──


@needs_the_database
async def test_releases_are_numbered_from_one_newest_first_and_ten_are_kept_beside_the_live_one(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, key_cache: KeyCache
) -> None:
    """Release 3 serves the app; twelve more later, the newest ten and release 3 are kept."""
    app = App(org=tenant.org, env=Env.production, name="support")
    await opened(sessions, key_cache, app, "first", "")
    async with sessions() as session:
        kept = [released.release for released in await list_releases(session, None, app)]
        (listed,) = await list_standing(session, Env.production, tenant.org)
        assert (await source_of(session, app, 1)).data == PROJECT
    assert [(row.release, row.note) for row in kept] == [(2, ""), (1, "first")]
    assert (kept[0].sha256, kept[0].bytes, listed.release) == (check_source(PROJECT).sha256, len(PROJECT), 2)
    source = check_source(PROJECT)
    async with sessions.begin() as session:
        await keep_release(session, app, source, author="m_ana", note="")
        serving = host_of(app.org, app.env, app.name, 3, source.sha256, "")
        await HostedAppRepository(session).mark_live(app.org, app.env, app.name, release=3, host=serving, runner="r_1")
        for _ in range(12):
            await keep_release(session, app, source, author="m_ana", note="")
    async with sessions() as session:
        still = [released.release.release for released in await list_releases(session, None, app)]
    assert still == [*range(15, 5, -1), 3]


@needs_the_database
async def test_an_app_nobody_hosts_has_nothing_to_keep_or_read(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, key_cache: KeyCache
) -> None:
    """The sandbox's app is not production's; an app nobody opened is not found by any verb."""
    await opened(sessions, key_cache, App(org=tenant.org, env=Env.sandbox, name="support"))
    nobody = App(org=tenant.org, env=Env.production, name="support")
    async with sessions.begin() as session:
        assert await list_standing(session, Env.production, tenant.org) == []
        with pytest.raises(NotFound, match="hosts no app called support"):
            await keep_release(session, nobody, check_source(PROJECT), author="m_ana", note="")
        with pytest.raises(NotFound, match="hosts no app called support"):
            await list_releases(session, None, nobody)
        with pytest.raises(NotFound, match="no release 3"):
            await source_of(session, nobody, 3)
