"""The processes: the gateway, a worker of the fleet, the fleet's overflow, the runner of hosted apps."""

import os
import signal
import subprocess
import sys
import threading
from types import FrameType
from typing import IO, override
from urllib.parse import urlparse

import typer
import uvicorn

from pinecall_runtime import runner, worker
from pinecall_runtime.app import announce_closing, app
from pinecall_runtime.cli.command import FOUND_WRONG, OK, context_of, verb
from pinecall_runtime.cli.output import Printer
from pinecall_runtime.config import Settings
from pinecall_runtime.exceptions import ConfigurationError
from pinecall_runtime.providers import service as providers

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
NOT_LOOPBACK = (
    "PINECALL_GATEWAY_URL binds {host}: a box's gateway listens on loopback, behind its proxy "
    "(a pod's says PINECALL_GATEWAY_LISTEN)"
)

# Google's load balancer keeps an idle connection to a gateway 600 s and sends the next request
# down it: the gateway must keep it longer (Google says 620 s), or a request meets a closed socket
# and the caller a 503.
KEEP_ALIVE_S = 620

worker_app = typer.Typer(help="a worker of the fleet PINECALL_FLEET names", no_args_is_help=True)
runner_app = typer.Typer(help="the runner of the env PINECALL_RUNNER_KEY opens", no_args_is_help=True)


# A stream never ends on its own: told nothing, a stop waits out uvicorn's grace and cuts it.
class Stopping(uvicorn.Server):
    """uvicorn's server, which tells the open streams when it is told to stop."""

    @override
    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        """Tell the streams, then stop as uvicorn does."""
        announce_closing(app)
        super().handle_exit(sig, frame)


@verb
async def gateway(ctx: typer.Context) -> int:
    """Serve the gateway, both envs: on loopback on a box, on PINECALL_GATEWAY_LISTEN in a pod."""
    settings = context_of(ctx).settings
    host, port = listening(settings)
    # The one proxy in front is believed alone: the box's on loopback, or a cluster's load balancer.
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxies,
        timeout_keep_alive=KEEP_ALIVE_S,
    )
    # Every plugin imported before the server listens: imported at the first endpoint that lists
    # the vendors (/metrics, /v1/providers) instead, the 45 held the loop 5 s while requests waited
    # (production, 2026-10-04).
    providers.installed()
    await Stopping(config).serve()
    return OK


@worker_app.command("start")
@verb
async def worker_start(ctx: typer.Context) -> int:
    """Answer the fleet's calls, until told to stop or cordoned."""
    return await worker.run_worker(context_of(ctx).settings)


@worker_app.command("overflow")
@verb
async def worker_overflow(ctx: typer.Context) -> int:
    """Answer when the fleet is full: one sentence and a call back offered, until told to stop."""
    return await worker.run_overflow(context_of(ctx).settings)


@runner_app.command("start")
@verb
async def runner_start(ctx: typer.Context) -> int:
    """Keep the env's hosted apps running, until told to stop."""
    return await runner.run_runner(context_of(ctx).settings)


# A box's gateway binds loopback and nothing else, its proxy being its one way in; a pod's binds
# what PINECALL_GATEWAY_LISTEN names, the cluster's load balancer being its way in.
def listening(settings: Settings) -> tuple[str, int]:
    """The host and port the gateway binds."""
    if settings.gateway_listen is not None:
        host, _, port = settings.gateway_listen.rpartition(":")
        return host.strip("[]"), int(port)
    bound = urlparse(settings.gateway_url)
    named = bound.hostname or "127.0.0.1"
    if named not in LOOPBACK:
        raise ConfigurationError(NOT_LOOPBACK.format(host=named))
    return named, bound.port or 8080


RUNNING = "Running. Ctrl-C stops it; `pinecall-runtime setup` starts it again."


# Two processes of this same package, their lines told apart by a prefix, stopped together.
def run_both(out: Printer, values: dict[str, str], *verbs: list[str]) -> int:
    """Run the verbs as child processes on the local settings until Ctrl-C; 1 when one failed."""
    children = [
        subprocess.Popen(
            [sys.executable, "-m", "pinecall_runtime.cli", *verb],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, **values},
        )
        for verb in verbs
    ]
    readers = [
        threading.Thread(target=_relay, args=(child.stdout, verb[0]), daemon=True)
        for child, verb in zip(children, verbs, strict=True)
    ]
    for reader in readers:
        reader.start()
    out.line(RUNNING)

    def stop(_signal: int, _frame: object) -> None:
        for child in children:
            child.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    codes = [child.wait() for child in children]
    for reader in readers:
        reader.join(timeout=1)
    return OK if all(code in (0, -signal.SIGTERM) for code in codes) else FOUND_WRONG


def _relay(out: IO[str] | None, prefix: str) -> None:
    if out is None:
        return
    for line in out:
        sys.stdout.write(f"{prefix:<8}| {line}")
        sys.stdout.flush()
