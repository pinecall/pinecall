"""The processes: the gateway, a worker of the fleet, the fleet's overflow, the runner of hosted apps."""

from types import FrameType
from typing import override

import typer
import uvicorn
from livekit.agents.utils import http_context

from runtime import runner, worker
from runtime.app import announce_closing, app
from runtime.cli.command import OK, context_of, verb
from runtime.providers.service import plugins

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
    host, port = settings.listening()
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
    plugins.list_vendors()
    # A written call runs its model here, outside any LiveKit job, and a plugin that opens its socket
    # with LiveKit's http session (OpenAI's `responses.LLM`) finds none: bound around the server, every
    # request's task inherits the one session, as a job's tasks do.
    async with http_context.open():
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
