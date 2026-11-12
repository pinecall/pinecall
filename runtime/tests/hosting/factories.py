"""What the hosting tests host: a project's sources as a tarball, and an app opened with its releases."""

import io
import os
import tarfile

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service.key_cache import KeyCache
from runtime.hosting.service.apps import App, open_app
from runtime.hosting.service.releases import check_source, keep_release
from runtime.kit.crypto import Vault

VAULT = Vault(os.environ["PINECALL_VAULT_KEY"])


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


async def opened(sessions: async_sessionmaker[AsyncSession], cache: KeyCache, app: App, *releases: str) -> None:
    """The app hosted, with a release per note given."""
    async with sessions.begin() as session:
        await open_app(session, VAULT, cache, app, created_by="m_ana")
        for note in releases:
            await keep_release(session, app, check_source(PROJECT), author="m_ana", note=note)
