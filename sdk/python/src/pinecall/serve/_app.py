"""The project's voice app in its serve entry: loaded after its agents, described, held."""

import asyncio
import importlib.util
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import TextIO, cast

from pinecall.agent import Agent
from pinecall.app import VoiceApp
from pinecall.bridge import Mounted, mount
from pinecall.client import Client
from pinecall.errors import DeclarationRefused
from pinecall.serve._loading import CannotServe, Flags, load_served
from pinecall.serve._paged import PAGE_PORT, Paging, serve_page
from pinecall.wire._names import Env
from pinecall.wire.events import AgentRegistered
from pinecall.wire.frames import WireModel

# A reload starts this process while the one before it drains, still on the port.
PORT_TRIES = 90
PORT_TRY_S = 0.5


@dataclass(frozen=True)
class Process:
    """What a served process holds its agents with: the client, the app, each class's slug."""

    client: Client
    app: VoiceApp | None
    slugs: Mapping[type, str]
    console: bool = False


def load_app(file: Path) -> VoiceApp:
    """The voice app the file defines: the one `voice_app(…)` it holds at its top level."""
    path = file.resolve()
    if not path.is_file():
        raise CannotServe(f"no voice app at {path}")
    spec = importlib.util.spec_from_file_location("pinecall_app", path)
    if spec is None or spec.loader is None:
        raise CannotServe(f"{path} is not a Python file")
    module = importlib.util.module_from_spec(spec)
    sys.modules["pinecall_app"] = module
    try:
        spec.loader.exec_module(module)
    except DeclarationRefused:
        raise
    except Exception as failed:
        raise CannotServe(f"{path} did not load: {type(failed).__name__}: {failed}") from failed
    apps = [one for one in vars(module).values() if isinstance(one, VoiceApp)]
    if len(apps) != 1:
        raise CannotServe(
            f"{path} is read as the project's voice app, and holds {len(apps) or 'none'} "
            'at its top level: app = voice_app("…") there, once, '
            "or give a file that is something else another name"
        )
    return apps[0]


def loaded(flags: Flags) -> tuple[list[tuple[str, type[Agent]]], VoiceApp | None]:
    """Every agent served with its slug, and the app, loaded after them so it imports them."""
    classes = [(served.slug, load_served(served)) for served in flags.served]
    if flags.app is None:
        return classes, None
    app = load_app(flags.app)
    for cls in app.agents():
        if not any(one is cls for _, one in classes):
            slugs = ", ".join(slug for slug, _ in classes)
            raise CannotServe(
                f"{app.name} answers a line with {cls.__name__}, and no agent served here is"
                f" that class ({slugs}): it is the Agent of its agents/<name>/agent.py"
            )
    return classes, app


def described(flags: Flags, out: TextIO) -> int:
    """`serve app`: the app's name and page, one line of JSON, for a CLI that never loads it."""
    classes, app = loaded(flags)
    if app is None:
        raise CannotServe("serve app takes --app, and one --slug for each --file")
    page = None
    if app.paged is not None:
        reached = app.paged.answers
        slug = next((slug for slug, cls in classes if cls is reached), None)
        if slug is None:
            raise CannotServe(f"{app.name}'s page reaches {reached.__name__}, which no agent is")
        page = {"dir": app.paged.dir, "agent": slug}
        if app.paged.only is not None:
            page["only"] = app.paged.only
    out.write(json.dumps({"name": app.name, "page": page}) + "\n")
    return 0


def held(process: Process, cls: type[Agent], slug: str, report: Callable[[str], None]) -> Mounted:
    """One agent held with what its app adds: its line's greeting, its team, the app's rules."""
    app, console = process.app, process.console
    if app is None:
        return mount(cls, process.client, slug=slug, takes_unclaimed=not console)
    mates = app.team_of(cls)
    mounted = mount(
        cls,
        process.client,
        slug=slug,
        takes_unclaimed=not console,
        declares=app.declares(cls),
        team={mate: process.slugs[mate] for mate in mates} if mates else None,
        rules=app.rules if cls in app.agents() else (),
        answers=app.choosing(cls),
    )
    pointed(mounted, app.numbers_of(cls), report)
    return mounted


# A number is the org's row: the app says who answers it, and the gateway says whether it is so.
def pointed(mounted: Mounted, numbers: Sequence[str], report: Callable[[str], None]) -> None:
    """Say once each number of the agent's lines the gateway does not point at it yet."""
    told: set[str] = set()

    def registered(event: WireModel, _: object) -> None:
        if not isinstance(event, AgentRegistered):
            return
        answered = {route.number for route in event.routes}
        for number in numbers:
            if number not in answered and number not in told:
                told.add(number)
                report(f"{number} is not pointed at this agent yet: `pinecall numbers` says where")

    mounted.agent.on("agent.registered", registered)


async def page_of(
    process: Process, file: Path, env: Mapping[str, str], err: TextIO
) -> ThreadingHTTPServer | None:
    """The app's page served here, unless a runner hosts the process: the platform serves that."""
    app = process.app
    paged = None if app is None else app.paged
    agent = None if paged is None else process.slugs.get(paged.answers)
    if app is None or paged is None or agent is None or env.get("PINECALL_HOST"):
        return None
    port = int(env.get("PINECALL_PAGE_PORT") or PAGE_PORT)
    client = process.client
    key, world = env.get("PINECALL_KEY", ""), cast("Env | None", client.env)
    # A page of one environment is not this one's: `pinecall start --prod` holds the app alone.
    if paged.only is not None and world is not None and paged.only != world:
        return None
    paging = Paging(file.parent / paged.dir, agent, client.url, key, world, port)
    for tried in range(PORT_TRIES + 1):
        try:
            serving = serve_page(paging)
        except OSError as failed:
            if tried < PORT_TRIES:
                await asyncio.sleep(PORT_TRY_S)
                continue
            err.write(
                f"{app.name}  its page is not served: {failed} (PINECALL_PAGE_PORT moves it)\n"
            )
            return None
        err.write(f"{app.name}  its page is at http://localhost:{port}\n")
        return serving
    return None
