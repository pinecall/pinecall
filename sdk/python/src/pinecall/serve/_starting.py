"""`serve start`: hold the agents named until asked to leave, then drain and close."""

import asyncio
from collections.abc import Mapping
from typing import TextIO

from pinecall.bridge import Mounted, mount
from pinecall.client import Client
from pinecall.serve._held import Held
from pinecall.serve._lines import drain_line, said
from pinecall.serve._loading import CannotServe, Flags, load_served
from pinecall.serve._viewing import answered
from pinecall.wire._names import Env, JsonObject
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
    return Client(url, key, world)


async def start(
    flags: Flags, out: TextIO, err: TextIO, env: Mapping[str, str], asked: asyncio.Queue[str]
) -> int:
    """Hold every agent named until a reason to leave arrives on `asked`; 0 once they left."""
    client = client_from(env, prod=flags.prod)
    classes = [(served.slug, load_served(served)) for served in flags.served]
    printer = said(client, out, err, events=flags.events)
    mounted: list[Mounted] = []
    for slug, cls in classes:
        held = mount(cls, client, slug=slug, takes_unclaimed=not flags.console)

        async def dev(
            verb: DevVerb, data: JsonObject, cls: type = cls, slug: str = slug
        ) -> JsonObject:
            return await answered(cls, slug, verb, data)

        held.agent.on_dev(dev)
        mounted.append(held)

    def stopped(why: str) -> None:
        err.write(why + "\n")
        asked.put_nowait(STOPPED)

    client.on_stopped(stopped)
    try:
        await client.connect()
        return await leave(Held(client, mounted), asked, err)
    finally:
        printer.close()


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
