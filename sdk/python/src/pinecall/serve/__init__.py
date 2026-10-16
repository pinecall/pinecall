"""The entry the one `pinecall` CLI starts a Python agent with, and `hold` for your own process."""

import asyncio
import logging
import os
import signal
import sys
import threading
from collections.abc import Mapping
from typing import TextIO

from pinecall.agent import Agent, LastCall
from pinecall.bridge import mount
from pinecall.client import Client
from pinecall.errors import DeclarationRefused, NotConnected, Refused
from pinecall.serve._held import Held
from pinecall.serve._loading import CannotServe, parse
from pinecall.serve._prompting import prompt
from pinecall.serve._starting import ENDED, SIGNALLED, client_from, start
from pinecall.wire._names import Env

USAGE = (
    "usage: python -m pinecall.serve start --file <agent.py> --slug <slug> [--file … --slug …]"
    " [--console] [--events] [--prod]\n"
    "       python -m pinecall.serve prompt --file <agent.py> --slug <slug> [--state field=json]…"
    " [--channel name] [--medium voice|text] [--show-machine]\n"
)


def main(
    argv: list[str],
    *,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
    env: Mapping[str, str] = os.environ,
) -> int:
    """Run one verb; 2 when it cannot run at all, with the sentence on `err`.

    `start` reads its door from `PINECALL_URL`, `PINECALL_KEY` and `PINECALL_ENV` alone, and leaves
    on SIGINT, SIGTERM or the end of its stdin, draining first; a second signal leaves now.
    """
    verb, rest = (argv[0], argv[1:]) if argv else ("", [])
    logged(env.get("PINECALL_LOG"))
    try:
        if verb == "prompt":
            return prompt(parse(rest), out)
        if verb == "start":
            return asyncio.run(started(rest, out, err, env))
    # A gateway that refuses the registration (a slug of another org, a key it does not take) is a
    # sentence for the person who ran it, not a traceback.
    except (CannotServe, DeclarationRefused, NotConnected, Refused) as refused:
        err.write(f"{refused}\n")
        return 2
    err.write(USAGE)
    return 2


def logged(level: str | None) -> None:
    """`PINECALL_LOG=debug` or `info`: the package's own log on stderr, each line timed."""
    if level in ("debug", "info"):
        logging.basicConfig(
            format="%(asctime)s.%(msecs)03d %(name)s %(message)s", datefmt="%H:%M:%S"
        )
        logging.getLogger("pinecall").setLevel(level.upper())


async def started(argv: list[str], out: TextIO, err: TextIO, env: Mapping[str, str]) -> int:
    """`start`, with the reasons to leave wired: the two signals, and the end of stdin."""
    flags = parse(argv)
    # What cannot run says so before a signal is trapped or stdin is watched.
    client_from(env, prod=flags.prod)
    asked: asyncio.Queue[str] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    for one in (signal.SIGINT, signal.SIGTERM):
        # A handler only pushes: the leaving is the main task's.
        loop.add_signal_handler(one, asked.put_nowait, SIGNALLED)

    def watched() -> None:
        # The CLI that started this process is gone when its end of the pipe closes; a stdin that
        # cannot be read at all says nothing about it.
        try:
            sys.stdin.read()
        except (OSError, ValueError):
            return
        loop.call_soon_threadsafe(asked.put_nowait, ENDED)

    threading.Thread(target=watched, daemon=True).start()
    return await start(flags, out, err, env, asked)


async def hold(
    cls: type[Agent],
    *,
    url: str,
    api_key: str,
    env: Env | None = None,
    last: LastCall | None = None,
) -> Held:
    """Hold an agent from your own process: mounted on a client of its own, and connected.

    ```python
    held = await pinecall.hold(ClinicaNorte, url="https://cloud.pinecall.io", api_key=key)
    ...
    await held.stop()  # drains: the live calls are handed over, not cut
    ```

    Args:
        cls: the agent's class.
        url: the gateway.
        api_key: a server's token, or a person's key.
        env: the world; a server's token needs none.
        last: where `last(contact)` reads a contact's previous call from.
    """
    client = Client(url, api_key, env)
    mounted = mount(cls, client, last=last)
    await client.connect()
    return Held(client, [mounted])
