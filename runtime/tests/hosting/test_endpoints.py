"""The hosting doors as the CLI reaches them: logs asked for while a stream is open, a release said once stored."""

import asyncio
import io
import tarfile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.calls.log.feeds import Feeds
from runtime.enums import Env
from runtime.hosting.models import HostedApp, HostedRelease
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


# I F7 (2026-10-23): a release's news went out before its row was committed, so the console, reading the
# release the moment it was told, could read the state before it and hear nothing more.
@needs_the_services
async def test_a_release_is_said_on_the_feed_once_it_is_stored(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession]
) -> None:
    feeds: Feeds = gateway.state["feeds"]
    feed = await feeds.reader_of(tenant.org, Env.sandbox)
    try:
        headers = {**tenant.server, "content-type": "application/gzip"}
        sent = await gateway.http.post("/v1/hosted/support/releases", content=a_project(), headers=headers)
        assert sent.status_code == 200, sent.text
        said = await asyncio.wait_for(anext(feed), 5.0)
        assert (said.type, said.data) == ("release.changed", {"app": "support", "release": sent.json()["release"]})
        async with sessions() as session:
            stored = await session.scalar(
                select(HostedRelease.release).where(HostedRelease.org == tenant.org, HostedRelease.name == "support")
            )
        assert stored == sent.json()["release"]
    finally:
        feed.close()


def a_project_with_a_page() -> bytes:
    """A release whose project built a page into ui/dist."""
    files = {
        "package.json": b"{}",
        "agents/support/agent.ts": b"export default 1",
        "ui/dist/index.html": b"<!doctype html><title>Support</title>",
        "ui/dist/assets/app.js": b"console.log(1)",
    }
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w:gz") as tar:
        for path, content in files.items():
            member = tarfile.TarInfo(path)
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))
    return packed.getvalue()


@needs_the_services
async def test_an_apps_page_is_served_at_the_apps_own_name_and_never_at_the_gateways(
    gateway: Gateway, tenant: Tenant
) -> None:
    """The page's files, its routes read as the page, its config, and a ticket asked of the app's own agent."""
    headers = {**tenant.server, "content-type": "application/gzip"}
    sent = await gateway.http.post(
        "/v1/hosted/support/releases",
        params={"page_dir": "ui/dist", "page_agent": "support"},
        content=a_project_with_a_page(),
        headers=headers,
    )
    assert sent.status_code == 200, sent.text
    name = f"support--{tenant.slug}--sandbox.pages.test"
    assert sent.json()["page_url"] == f"https://{name}/"
    at_its_name = {"host": name}

    page = await gateway.http.get("/", headers=at_its_name)
    assert (page.status_code, page.headers["cache-control"]) == (200, "no-store")
    assert "<title>Support</title>" in page.text
    asset = await gateway.http.get("/assets/app.js", headers=at_its_name)
    assert (asset.status_code, asset.text) == (200, "console.log(1)")
    assert "javascript" in asset.headers["content-type"]
    assert "<title>Support</title>" in (await gateway.http.get("/visits/3", headers=at_its_name)).text
    assert (await gateway.http.get("/missing.png", headers=at_its_name)).status_code == 404

    config = await gateway.http.get("/pinecall/config", headers=at_its_name)
    assert config.json() == {"agent": "support", "turnstile": None}
    # Nobody holds the agent in this test: the ticket is asked of it, and refused for that alone.
    ticket = await gateway.http.post("/pinecall/token", json={"scope": "chat"}, headers=at_its_name)
    assert ticket.status_code == 404, ticket.text
    assert "support" in ticket.text
    # A visitor dictates into the page's field: the socket is the gateway's own, a minute long.
    dictation = await gateway.http.post("/pinecall/dictation", json={"language": "es"}, headers=at_its_name)
    assert dictation.status_code == 200, dictation.text
    assert "/v1/transcriptions/stream?token=" in dictation.json()["url"]
    assert (dictation.json()["url"].split(":")[0], dictation.json()["hear"]) in (("ws", []), ("wss", []))

    # The same routes asked at the gateway's own name answer nothing: a page is never the console's document.
    assert (await gateway.http.get(f"/v1/pages/{name}/files/")).status_code == 404
    assert (await gateway.http.get("/", headers={"host": "nobody--here.pages.test"})).status_code == 404
