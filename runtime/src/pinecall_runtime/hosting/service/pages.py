"""An app's page: the folder of its release the gateway serves at the app's own name, and whose name that is."""

import io
import mimetypes
import tarfile
from collections import OrderedDict
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.hosting.models import HostedRelease
from pinecall_runtime.hosting.repository import HostedAppRepository, ReleaseRepository
from pinecall_runtime.hosting.service.apps import App, Source
from pinecall_runtime.kit.text import parse_slug

# A slug never holds two dashes in a row, so the app, its org and its env are read back off one label.
BETWEEN = "--"
THE_SANDBOX = "sandbox"
# What DNS allows one label.
LONGEST_LABEL = 63
INDEX = "index.html"
LARGEST_PAGE = 20 * 1024 * 1024
# The pages kept unpacked in this process: the newest asked for, each one release's.
PAGES_KEPT = 8

NO_INDEX = "the page's folder {dir} has no index.html in what was sent: build the page, then deploy"
NOT_A_FOLDER = "a page's folder is inside the project, like ui/dist, and {dir!r} is not"
PAGE_TOO_BIG = "the page's folder {dir} unpacks to more than {limit} MiB"
NAME_TOO_LONG = (
    "{label} is too long a name for a page: an app's name and its org's make one of {limit} characters at most"
)
NO_PAGE = "no page is served at this name"
NO_FILE = "the page has no file {path}"


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


class _Unpacked:
    """The pages unpacked in this process, by the sha256 of the release and the folder: the oldest asked for goes."""

    def __init__(self, most: int) -> None:
        self.most = most
        self.kept: OrderedDict[tuple[str, str], dict[str, bytes]] = OrderedDict()

    def of(self, sha256: str, folder: str) -> dict[str, bytes] | None:
        found = self.kept.get((sha256, folder))
        if found is not None:
            self.kept.move_to_end((sha256, folder))
        return found

    def keep(self, sha256: str, folder: str, files: dict[str, bytes]) -> None:
        self.kept[(sha256, folder)] = files
        while len(self.kept) > self.most:
            self.kept.popitem(last=False)


_UNPACKED = _Unpacked(PAGES_KEPT)


def label_of(org_slug: str, app: App) -> str:
    """The one label an app's page is named by under the pages' domain."""
    parts = [app.name, org_slug, *([THE_SANDBOX] if app.env is Env.sandbox else [])]
    return BETWEEN.join(parts)


def named_by(host: str, domain: str) -> tuple[str, str, Env] | None:
    """The org's slug, the app and the env a host names under the pages' domain; None for any other host."""
    label, dot, under = host.lower().partition(".")
    if dot == "" or under != domain.lower():
        return None
    parts = label.split(BETWEEN)
    env = Env.sandbox if len(parts) == 3 and parts[2] == THE_SANDBOX else Env.production
    if len(parts) != (3 if env is Env.sandbox else 2) or not all(parts):
        return None
    return parts[1], parts[0], env


def checked_page(source: Source, folder: str | None, agent: str | None, label: str) -> Page | None:
    """The page a release was sent with, checked against its sources; None for a release sent with none."""
    if folder is None and agent is None:
        return None
    if not folder or not agent:
        raise ValidationError("a page is sent with both its folder and its agent: page_dir and page_agent")
    named = folder.strip("/")
    if named == "" or folder.startswith("/") or ".." in named.split("/"):
        raise ValidationError(NOT_A_FOLDER.format(dir=folder))
    if len(label) > LONGEST_LABEL:
        raise ValidationError(NAME_TOO_LONG.format(label=label, limit=LONGEST_LABEL))
    if INDEX not in _files_under(source.data, named):
        raise ValidationError(NO_INDEX.format(dir=named))
    return Page(dir=named, agent=parse_slug(agent))


async def page_at(session: AsyncSession, app: App) -> Paged:
    """The page the app serves now, from the release that runs; NotFound for an app with none."""
    hosted = await HostedAppRepository(session).get(app.org, app.env, app.name)
    if hosted is None:
        raise NotFound(NO_PAGE)
    release = await ReleaseRepository(session).paged(app.org, app.env, app.name, hosted.live_release)
    if release is None or release.page_dir is None or release.page_agent is None:
        raise NotFound(NO_PAGE)
    page = Page(dir=release.page_dir, agent=release.page_agent)
    return Paged(app=app, release=release.release, sha256=release.sha256, page=page)


async def file_of(session: AsyncSession, paged: Paged, path: str) -> PageFile:
    """One file of the page; a path that names no file is the page itself, so its own router reads it."""
    files = _UNPACKED.of(paged.sha256, paged.page.dir)
    if files is None:
        files = _files_under(await _sources(session, paged), paged.page.dir)
        _UNPACKED.keep(paged.sha256, paged.page.dir, files)
    asked = path.strip("/")
    name = asked if asked in files else INDEX
    # A file asked for by its extension and not there is missing; a route of the page's own is the page.
    if name != asked and "." in asked.rsplit("/", 1)[-1]:
        raise NotFound(NO_FILE.format(path=asked))
    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return PageFile(body=files[name], media_type=media_type, is_the_page=name == INDEX)


async def _sources(session: AsyncSession, paged: Paged) -> bytes:
    app = paged.app
    found: HostedRelease | None = await ReleaseRepository(session).get(app.org, app.env, app.name, paged.release)
    if found is None:
        raise NotFound(NO_PAGE)
    return bytes(found.source)


# The sources were checked when they were kept: every member is a file or a folder inside the project.
def _files_under(data: bytes, folder: str) -> dict[str, bytes]:
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
                raise ValidationError(PAGE_TOO_BIG.format(dir=folder, limit=LARGEST_PAGE >> 20))
            read = tarball.extractfile(member)
            if read is not None:
                files[name.removeprefix(inside)] = read.read()
    return files
