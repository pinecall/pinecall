"""`serve start`: hold the agents named until asked to leave, then drain and close."""

import asyncio
from collections.abc import Callable, Mapping
from typing import TextIO, cast

from pinecall._app_work import AppDoor
from pinecall._docs import push_declared_docs
from pinecall._flow_loop import Working, entry_heard, pass_heard, work
from pinecall._melody import upload_declared_hold
from pinecall.app import VoiceApp
from pinecall.bridge import Mounted
from pinecall.client import Client
from pinecall.serve._app import Process, held, loaded, page_of
from pinecall.serve._held import Held
from pinecall.serve._lines import drain_line, said
from pinecall.serve._loading import CannotServe, Flags
from pinecall.serve._masking import Masking
from pinecall.serve._viewing import answered
from pinecall.wire._names import Env, JsonObject
from pinecall.wire.frames import Entry
from pinecall.wire.parts import DevVerb

NO_DOOR = (
    "serve start reads PINECALL_URL and PINECALL_KEY from its environment, and one was not set"
)

WORLDS: tuple[Env, ...] = ("sandbox", "production")

# Why the process is asked to leave: a signal, the CLI that started it gone, or the org's stop.
SIGNALLED, ENDED, STOPPED = "signalled", "ended", "stopped"


def client_from(env: Mapping[str, str], *, prod: bool) -> Client:
    """The door from the environment alone: never a flag, never a file."""
    url, key = env.get("PINECALL_URL", ""), env.get("PINECALL_KEY", "")
    if not url or not key:
        raise CannotServe(NO_DOOR)
    world = "production" if prod else env.get("PINECALL_ENV") or None
    if world is not None and world not in WORLDS:
        raise CannotServe(f"PINECALL_ENV is sandbox or production, not {world}")
    client = Client(url, key, world)
    # The name a hosted app's runner gave it: the gateway knows the release by it.
    client.host = env.get("PINECALL_HOST") or client.host
    return client


async def start(
    flags: Flags, out: TextIO, err: TextIO, env: Mapping[str, str], asked: asyncio.Queue[str]
) -> int:
    """Hold every agent named until a reason to leave arrives on `asked`; 0 once they left."""
    client = client_from(env, prod=flags.prod)
    classes, app = loaded(flags)
    slugs: dict[type, str] = {cls: slug for slug, cls in classes}
    process = Process(client, app, slugs, console=flags.console)
    mounted: list[Mounted] = []
    for slug, cls in classes:
        one = held(process, cls, slug, _said_as(err, slug))

        async def dev(
            verb: DevVerb, data: JsonObject, cls: type = cls, slug: str = slug
        ) -> JsonObject:
            return await answered(cls, slug, verb, data)

        one.agent.on_dev(dev)
        mounted.append(one)
    masking = {one.slug: Masking(one.agent.config) for one in mounted}
    printer = said(client, out, err, masking, events=flags.events)
    working = None if app is None else working_of(process, app, env, err)

    def stopped(why: str) -> None:
        err.write(why + "\n")
        asked.put_nowait(STOPPED)

    client.on_stopped(stopped)
    tasks: list[asyncio.Task[None]] = []
    page = None
    try:
        if working is not None:
            client.on_entries(
                lambda entry: tasks.append(asyncio.ensure_future(heard(working, entry)))
            )
        await client.connect()
        # The documents a class declares as its base, once per process, before any call.
        for slug, cls in classes:
            await push_declared_docs(client, cls, _said_as(err, slug))
            await upload_declared_hold(client, cls, slug, _said_as(err, slug))
        if app is not None and flags.app is not None:
            page = await page_of(process, flags.app, env, err)
        # The gateway is asked for work only by an app that has flows: the rest keep the socket.
        if working is not None and app is not None and app.flows():
            tasks.append(asyncio.ensure_future(work(working)))
        return await leave(Held(client, mounted), asked, err)
    finally:
        for task in tasks:
            task.cancel()
        if page is not None:
            page.shutdown()
        printer.close()


def working_of(process: Process, app: VoiceApp, env: Mapping[str, str], err: TextIO) -> Working:
    """What the app's loop runs with: its door, each class's slug, and its own lines on `err`."""
    client = process.client
    world = cast("Env | None", client.env)
    door = AppDoor(client.url, env.get("PINECALL_KEY", ""), world, app.name)

    def report(line: str) -> None:
        err.write(f"{app.name}  {line}\n")

    return Working(app, door, process.slugs.get, report)


async def heard(working: Working, entry: Entry) -> None:
    """What an app's agents log and what happens to their calls reaches its handlers and flows."""
    report = working.report
    await working.app.heard(
        entry.type, entry.call, entry.agent, entry.data,
        lambda name, error: report(f"the handler of {name} raised: {error}"),
    )  # fmt: skip
    await entry_heard(working, entry)
    await pass_heard(working, entry)


def _said_as(err: TextIO, slug: str) -> Callable[[str], None]:
    def say(line: str) -> None:
        err.write(f"{slug}  {line}\n")

    return say


async def leave(held: Held, asked: asyncio.Queue[str], err: TextIO) -> int:
    """The first reason drains (the org's stop closes at once); only a second signal cuts the drain.

    The end of stdin after a signal is not a second one: the CLI passes a signal on and closes the
    pipe together.
    """
    if await asked.get() == STOPPED:
        await held.close()
        return 0
    draining = asyncio.ensure_future(held.stop())
    while True:
        again = asyncio.ensure_future(asked.get())
        done, _ = await asyncio.wait({draining, again}, return_when=asyncio.FIRST_COMPLETED)
        if draining in done:
            again.cancel()
            err.write(drain_line(draining.result()) + "\n")
            err.flush()
            return 0
        if again.result() == SIGNALLED:
            draining.cancel()
            await held.close()
            return 0
