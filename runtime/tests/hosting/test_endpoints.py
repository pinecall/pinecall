"""The hosting doors as the CLI reaches them: an app's logs asked for while the stream stays open."""

import io
import tarfile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.hosting.models import HostedApp
from tests.conftest import Gateway, Tenant, needs_the_services


def a_project() -> bytes:
    """A gzipped tarball a release takes."""
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w:gz") as tar:
        for path, content in {"package.json": b"{}", "agents/support/agent.ts": b"export default 1"}.items():
            member = tarfile.TarInfo(path)
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))
    return packed.getvalue()


@needs_the_services
async def test_asking_for_logs_is_committed_while_the_stream_is_still_open(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The runner reads the ask on its next beat: an ask held in the stream's transaction never reached it."""
    headers = {**tenant.server, "content-type": "application/gzip"}
    sent = await gateway.http.post("/v1/hosted/support/releases", content=a_project(), headers=headers)
    assert sent.status_code == 200, sent.text
    streaming = {**tenant.server, "accept": "text/event-stream"}
    async with gateway.http.stream("GET", "/v1/hosted/support/logs", headers=streaming) as followed:
        assert followed.status_code == 200
        lines = followed.aiter_lines()
        assert (await anext(lines)).startswith("retry:")
        async with sessions() as session:
            asked = await session.scalar(
                select(HostedApp.logs_asked_at).where(HostedApp.org == tenant.org, HostedApp.name == "support")
            )
        assert asked is not None
