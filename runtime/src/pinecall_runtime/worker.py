"""The worker process: livekit's AgentServer under its fleet's name, and the fleet's overflow."""

import asyncio
import logging
import signal

from livekit.agents import AgentServer, JobContext, JobProcess

from pinecall_runtime.config import Settings, load_settings
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.jobs import service as jobs
from pinecall_runtime.livekit import key_pair
from pinecall_runtime.providers import service as providers
from pinecall_runtime.wire.dispatch import Dispatch

logger = logging.getLogger(__name__)

# Under the pod's terminationGracePeriodSeconds (15 min): livekit's hour would end in a SIGKILL
# and calls with no call.ended. What is still running after it is shut down and sealed as drained.
DRAIN_S = 10 * 60

# What a job has to seal once told to stop: livekit's 10 s kills a seal halfway.
SEALING_S = 60.0

# A new process warms up while others are busy: livekit's own 10 s kills it while three pools warm
# up at once on a loaded box, then respawns it for ever.
INITIALIZE_S = 90.0

# The overflow is offered a call only by the gateway, by its name, when no worker of the fleet has
# a seat: it never reads itself full.
OPEN = 0.0

STILL_UP = "%d calls outlived the drain of %.0f s: shut down and sealed as drained"


# Module-level: livekit pickles the entrypoint by module and name, so the gateway it reaches is
# built in the job's own process.
async def run_job(ctx: JobContext) -> None:
    """Every job of the fleet: one call, or telling the caller of a call whose worker went away."""
    settings = load_settings()
    gateway = _gateway_of(ctx.proc, settings)
    dispatch = Dispatch.parse(ctx.job.metadata)
    if dispatch.worker_gone:
        await jobs.tell_the_caller(ctx, gateway, settings, dispatch)
        return
    await jobs.answer_job(ctx, gateway, settings)


async def run_overflow_job(ctx: JobContext) -> None:
    """One call the fleet had no seat for, or one whose worker went away."""
    settings = load_settings()
    await jobs.answer_overflow(ctx, _gateway_of(ctx.proc, settings), settings)


# A process is warmed before a job reaches it: the gateway's client and the tracer are its own.
def prewarm(proc: JobProcess) -> None:
    """Ready a process for its jobs."""
    settings = load_settings()
    proc.userdata["gateway"] = _gateway(settings)
    proc.userdata["spans"] = jobs.trace_to(settings)


def worker_server(settings: Settings) -> AgentServer:
    """The AgentServer of this worker, registered under its own name in its fleet."""
    key, secret = _registrable(settings)
    server = AgentServer(
        ws_url=settings.livekit_url,
        api_key=key,
        api_secret=secret,
        drain_timeout=DRAIN_S,
        shutdown_process_timeout=SEALING_S,
        initialize_process_timeout=INITIALIZE_S,
        host=settings.worker_http_host,
        port=settings.worker_http_port,
        setup_fnc=prewarm,
        # LiveKit's own line stands, on both of its sides; Load reports on its scale.
        load_fnc=jobs.Load(settings.max_jobs),
    )
    # livekit keeps one warm process per CPU; two fleets on one machine hold twice the memory.
    if settings.idle_processes is not None:
        server.update_options(num_idle_processes=settings.idle_processes)
    # The gateway chooses the worker and dispatches to its name (fleet/).
    server.rtc_session(run_job, agent_name=jobs.agent_name_of(settings))
    return server


def overflow_server(settings: Settings) -> AgentServer:
    """The overflow's AgentServer, under <fleet>/overflow, on any free port, always open."""
    key, secret = _registrable(settings)
    server = AgentServer(
        ws_url=settings.livekit_url,
        api_key=key,
        api_secret=secret,
        initialize_process_timeout=INITIALIZE_S,
        host="127.0.0.1",
        port=0,
        setup_fnc=prewarm,
        load_fnc=_always_open,
    )
    server.rtc_session(run_overflow_job, agent_name=fleet.overflow_name(settings.fleet))
    return server


async def run_worker(settings: Settings) -> int:
    """Run the worker until it is told to stop or cordoned; the exit it leaves with."""
    server = worker_server(settings)
    gateway = _gateway(settings)
    minute = jobs.LastMinute()
    measures = jobs.measures_path(settings)
    hearing = await jobs.listen_for_jobs(measures, minute)
    beats = jobs.Heartbeats(server, gateway, settings, minute)
    stopping = _stop_on_a_signal()
    running = asyncio.create_task(server.run())
    beating = asyncio.create_task(beats.run())
    ready = asyncio.create_task(jobs.announce_ready(beats, settings.notify_socket))
    waits = {running, asyncio.create_task(stopping.wait()), asyncio.create_task(beats.leave.wait())}
    await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    try:
        await server.drain(DRAIN_S)
    except TimeoutError:
        # livekit raises when the drain runs out; the close is what shuts and seals the calls left.
        logger.warning(STILL_UP, len(server.active_jobs), DRAIN_S)
    await server.aclose()
    for task in (*waits, beating, ready):
        task.cancel()
    hearing.close()
    measures.unlink(missing_ok=True)
    await gateway.aclose()
    return jobs.CORDONED_EXIT if beats.cordoned else 0


async def run_overflow(settings: Settings) -> int:
    """Run the overflow until told to stop: the gateway sends it calls no worker has a seat for."""
    server = overflow_server(settings)
    stopping = _stop_on_a_signal()
    running = asyncio.create_task(server.run())
    await asyncio.wait({running, asyncio.create_task(stopping.wait())}, return_when=asyncio.FIRST_COMPLETED)
    await server.aclose()
    return 0


# URL and pair are handed over: AgentServer reads os.environ, and the .env files are not in it.
def _registrable(settings: Settings) -> tuple[str, str]:
    pair = key_pair(settings)
    # Every plugin imported in the worker's own process is one livekit lists in its forkserver's
    # preload: imported once there, inherited by each call's process. Imported in the call's
    # process instead, they held its loop 3-5 s on an idle box, up to 70 s on a loaded one, while
    # the caller waited (the load lab, 2026-10-01).
    providers.installed()
    return pair


def _always_open(_server: AgentServer) -> float:
    return OPEN


def _gateway(settings: Settings) -> jobs.GatewayClient:
    key = None if settings.worker_key is None else settings.worker_key.get_secret_value()
    return jobs.gateway_at(settings.gateway_url, key)


def _gateway_of(proc: JobProcess, settings: Settings) -> jobs.GatewayClient:
    warmed: object = proc.userdata.get("gateway")
    return warmed if isinstance(warmed, jobs.GatewayClient) else _gateway(settings)


def _stop_on_a_signal() -> asyncio.Event:
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(stop, stopping.set)
    return stopping
