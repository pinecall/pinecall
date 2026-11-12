"""An app's page: the folder of its release the gateway serves at the app's own name, and who visits it."""

import asyncio
import io
import mimetypes
import tarfile
from collections import OrderedDict
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.enums import Env, KeyScope
from runtime.exceptions import NotFound, ValidationError
from runtime.hosting.repository import HostedAppRepository, ReleaseRepository
from runtime.hosting.service.apps import App
from runtime.kit.text import parse_slug
from runtime.platform import service as platform
from runtime.scoping import scope_to
from runtime.signin import service as signin

# A slug never holds two dashes in a row, so the app, its org and its env are read back off one label.
BETWEEN = "--"
THE_SANDBOX = "sandbox"
# What DNS allows one label.
LONGEST_LABEL = 63
INDEX = "index.html"
LARGEST_PAGE = 20 * 1024 * 1024
# The pages kept unpacked in one process: the newest asked for, up to this many bytes of files.
PAGES_KEPT_BYTES = 64 * 1024 * 1024
# How many tickets and codes one address is given in a minute.
TICKETS_A_MINUTE = 6


@dataclass(frozen=True, slots=True)
class Page:
    """What a release says of its page: the folder inside its sources, and the agent a visitor reaches."""

    dir: str
    agent: str


@dataclass(frozen=True, slots=True)
class Paged:
    """A page being served: whose it is, and the release it is read from."""

    app: App
    release: int
    sha256: str
    page: Page


@dataclass(frozen=True, slots=True)
class PageFile:
    """One file of a page, as it is answered."""

    body: bytes
    media_type: str
    # The page itself, read again on every visit; anything else is a built asset.
    is_the_page: bool


def label_page(org_slug: str, app: App) -> str:
    """The one label an app's page is named by under the pages' domain."""
    parts = [app.name, org_slug, *([THE_SANDBOX] if app.env is Env.sandbox else [])]
    return BETWEEN.join(parts)


def url_of(label: str, domain: str | None) -> str | None:
    """Where the page of that label is served; None on a box that serves no pages."""
    return None if domain is None else f"https://{label}.{domain}/"


def read_page_name(host: str, domain: str) -> tuple[str, str, Env] | None:
    """The org's slug, the app and the env a host names under the pages' domain; None for any other host."""
    label, dot, under = host.lower().partition(".")
    if dot == "" or under != domain.lower():
        return None
    parts = label.split(BETWEEN)
    env = Env.sandbox if len(parts) == 3 and parts[2] == THE_SANDBOX else Env.production
    if len(parts) != (3 if env is Env.sandbox else 2) or not all(parts):
        return None
    return parts[1], parts[0], env


# It unpacks the sources: called in a thread by whoever keeps a release.
def check_page(source: bytes, folder: str | None, agent: str | None, label: str) -> Page | None:
    """The page a release was sent with, checked against its sources; None for a release sent with none."""
    if folder is None and agent is None:
        return None
    if not folder or not agent:
        raise ValidationError("a page is sent with both its folder and its agent: page_dir and page_agent")
    named = folder.strip("/")
    if named == "" or folder.startswith("/") or ".." in named.split("/"):
        raise ValidationError(f"a page's folder is inside the project, like ui/dist, and {folder!r} is not")
    if len(label) > LONGEST_LABEL:
        raise ValidationError(
            f"{label} is too long a name for a page: an app's name and its org's make one of {LONGEST_LABEL} "
            "characters at most"
        )
    if INDEX not in _unpack_folder(source, named):
        raise ValidationError(
            f"the page's folder {named} has no index.html in what was sent: build the page, then deploy"
        )
    return Page(dir=named, agent=parse_slug(agent))


# The request names no org: the org is read as the box reads, and what follows as that org alone. A
# page answers only the name the request came in by, so a tenant's page is never a document of the
# console's origin.
async def resolve_page(session: AsyncSession, domain: str | None, host: str, came_in_by: str) -> Paged:
    """The page a request by an app's own name reaches; NotFound for any other name."""
    named = None if domain is None else read_page_name(host, domain)
    if named is None or came_in_by.split(":")[0].lower() != host.lower():
        raise NotFound("no page is served at this name")
    slug, name, env = named
    org = await accounts.find_org(session, slug)
    if org is None or org.slug != slug:
        raise NotFound("no page is served at this name")
    scope_to(org.id)
    return await find_page(session, App(org=org.id, env=env, name=name))


async def find_page(session: AsyncSession, app: App) -> Paged:
    """The page the app serves now, from the release that runs; NotFound for an app with none."""
    hosted = await HostedAppRepository(session).find(app.org, app.env, app.name)
    if hosted is None:
        raise NotFound("no page is served at this name")
    release = await ReleaseRepository(session).find_serving_page(app.org, app.env, app.name, hosted.live_release)
    if release is None or release.page_dir is None or release.page_agent is None:
        raise NotFound("no page is served at this name")
    page = Page(dir=release.page_dir, agent=release.page_agent)
    return Paged(app=app, release=release.release, sha256=release.sha256, page=page)


# A visitor holds no key: the page's own name is what lets them in, as far as one call with its agent.
def visitor_of(paged: Paged) -> Actor:
    """Who a visitor of the page acts as: the page's org and env, with the one scope of talking to it."""
    app = paged.app
    key_id = f"page:{app.org}:{app.env.value}:{app.name}"
    return Actor(key_id=key_id, org=app.org, env=app.env, scopes=frozenset({KeyScope.talk}), label="page")


async def admit_visitor(
    tickets: platform.AttemptThrottle, turnstile: signin.Turnstile, host: str, token: str | None, client: str
) -> None:
    """Let one address ask for a ticket or a code: so many a minute, and past the captcha where the box asks one."""
    await tickets.check(f"{client} page", "calls from here")
    await turnstile.check(token, "page", client, on=host.lower())


class Pages:
    """The pages unpacked in this process, by release and folder: the one asked for longest ago goes first."""

    def __init__(self, most_bytes: int = PAGES_KEPT_BYTES) -> None:
        """Nothing unpacked yet."""
        self.most_bytes = most_bytes
        self._kept: OrderedDict[tuple[str, str], dict[str, bytes]] = OrderedDict()
        # One unpacking at a time per page: the requests that arrive together wait for the first.
        self._unpacking: dict[tuple[str, str], asyncio.Lock] = {}

    async def file_of(self, session: AsyncSession, paged: Paged, path: str) -> PageFile:
        """One file of the page; a path that names no file is the page itself, so its own router reads it."""
        files = await self._files_of(session, paged)
        asked = path.strip("/")
        name = asked if asked in files else INDEX
        # A file asked for by its extension and not there is missing; a route of the page's own is the page.
        if name != asked and "." in asked.rsplit("/", 1)[-1]:
            raise NotFound(f"the page has no file {asked}")
        media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return PageFile(body=files[name], media_type=media_type, is_the_page=name == INDEX)

    # Unpacked in a thread, once: a tarball of megabytes on the loop would hold every call of the gateway
    # for as long as it takes, at a route anybody reaches with no key.
    async def _files_of(self, session: AsyncSession, paged: Paged) -> dict[str, bytes]:
        key = (paged.sha256, paged.page.dir)
        found = self._find(key)
        if found is not None:
            return found
        async with self._unpacking.setdefault(key, asyncio.Lock()):
            found = self._find(key)
            if found is None:
                found = await asyncio.to_thread(_unpack_folder, await _read_sources(session, paged), paged.page.dir)
                self._keep(key, found)
        self._unpacking.pop(key, None)
        return found

    def _find(self, key: tuple[str, str]) -> dict[str, bytes] | None:
        found = self._kept.get(key)
        if found is not None:
            self._kept.move_to_end(key)
        return found

    def _keep(self, key: tuple[str, str], files: dict[str, bytes]) -> None:
        self._kept[key] = files
        while len(self._kept) > 1 and sum(_size_of(kept) for kept in self._kept.values()) > self.most_bytes:
            self._kept.popitem(last=False)


async def _read_sources(session: AsyncSession, paged: Paged) -> bytes:
    app = paged.app
    found = await ReleaseRepository(session).find(app.org, app.env, app.name, paged.release)
    if found is None:
        raise NotFound("no page is served at this name")
    return bytes(found.source)


def _size_of(files: dict[str, bytes]) -> int:
    return sum(len(body) for body in files.values())


# The sources were checked when they were kept: every member is a file or a folder inside the project.
def _unpack_folder(data: bytes, folder: str) -> dict[str, bytes]:
    inside = f"{folder}/"
    files: dict[str, bytes] = {}
    unpacked = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tarball:
        for member in tarball:
            name = member.name.removeprefix("./")
            if not member.isfile() or not name.startswith(inside):
                continue
            unpacked += member.size
            if unpacked > LARGEST_PAGE:
                raise ValidationError(f"the page's folder {folder} unpacks to more than {LARGEST_PAGE >> 20} MiB")
            read = tarball.extractfile(member)
            if read is not None:
                files[name.removeprefix(inside)] = read.read()
    return files
