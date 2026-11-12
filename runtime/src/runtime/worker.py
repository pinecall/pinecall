"""The worker process: livekit's AgentServer under its fleet's name, its heartbeat, and the fleet's overflow."""

import asyncio
import logging
from pathlib import Path

import httpx
from livekit.agents import AgentServer, JobContext, JobProcess

from runtime import builders
from runtime.config import Settings, load_settings
from runtime.fleet import service as fleet
from runtime.jobs import service as jobs
from runtime.jobs import tasks as jobs_tasks
from runtime.kit.loops import Loops
from runtime.kit.signals import stop_on_a_signal
from runtime.livekit import key_pair
from runtime.providers import service as providers

logger = logging.getLogger(__name__)

# Under the pod's terminationGracePeriodSeconds (15 min): livekit's hour would end in a SIGKILL
# and calls with no call.ended. What is still running after it is shut down and sealed as drained.
DRAIN_S = 10 * 60

# A new process warms up while others are busy: livekit's own 10 s kills it while three pools warm
# up at once on a loaded box, then respawns it for ever.
INITIALIZE_S = 90.0

# The overflow is offered a call only by the gateway, by its name, when no worker of the fleet has
# a place: it never reads itself full.
OPEN = 0.0

# The one name a process's readied state is kept under, in livekit's dictionary for it.
WARMED = "warmed"

STILL_UP = "%d calls outlived the drain of %.0f s: shut down and sealed as drained"


# Module-level: livekit pickles an entrypoint by module and name, so what it reaches is built in
# the job's own process, by `prewarm`.
async def run_job(ctx: JobContext) -> None:
    """Every job of the fleet: one call, or telling the caller of a call whose worker went away."""
    await jobs.take_job(ctx, _get_warmed(ctx.proc), jobs.answer_job)


async def run_overflow_job(ctx: JobContext) -> None:
    """One call the fleet had no place for, or one whose worker went away."""
    await jobs.take_job(ctx, _get_warmed(ctx.proc), jobs.answer_overflow)


# livekit runs it alone, after it closed the session and before it leaves the room, within
# `session_end_timeout`: the call's last entry, its seal and its room, in that order.
async def end_job(ctx: JobContext) -> None:
    """The end of a job's call: closed, sealed, its room let go."""
    await jobs.end_job(_get_warmed(ctx.proc))


# A process is readied before a job reaches it: the gateway's client, the tracer and the place
# recordings are kept are its own, built once from the settings.
def prewarm(proc: JobProcess) -> None:
    """Ready a process for its jobs."""
    settings = load_settings()
    headers = None if settings.otlp_headers is None else settings.otlp_headers.get_secret_value()
    told = jobs.JobSettings(
        agent=settings.agent,
        app=settings.app,
        zone=settings.timezone,
        recordings_root=Path(settings.recordings_root),
        voice_lookup_budget_ms=settings.voice_lookup_budget_ms,
        text_lookup_budget_ms=settings.text_lookup_budget_ms,
        tool_steps=settings.max_tool_steps,
        overflow_says=settings.overflow_says,
        worker=jobs.worker_name_of(settings.worker_name),
        measures=jobs.measures_path(settings.fleet, settings.worker_http_port),
    )
    proc.userdata[WARMED] = jobs.Warmed(
        gateway=_gateway(settings),
        spans=jobs.trace_to(settings.otlp_endpoint, headers, fleet=settings.fleet, pii=settings.otlp_pii),
        recordings=builders.build_recordings(settings, httpx.AsyncClient()),
        told=told,
    )


def worker_server(settings: Settings, load: jobs.Load) -> AgentServer:
    """The AgentServer of this worker, registered under its own name in its fleet."""
    key, secret = key_pair(settings)
    preload_plugins()
    server = AgentServer(
        ws_url=settings.livekit_url,
        api_key=key,
        api_secret=secret,
        drain_timeout=DRAIN_S,
        session_end_timeout=jobs.A_JOB_ENDS_WITHIN_S,
        initialize_process_timeout=INITIALIZE_S,
        host=settings.worker_http_host,
        port=settings.worker_http_port,
        setup_fnc=prewarm,
        # LiveKit's own line stands, on both of its sides; Load reports on its scale.
        load_fnc=load,
    )
    # livekit keeps one warm process per CPU; two fleets on one machine hold twice the memory.
    if settings.idle_processes is not None:
        server.update_options(num_idle_processes=settings.idle_processes)
    # The gateway chooses the worker and dispatches to its name (fleet/).
    name = jobs.agent_name_of(settings.fleet, jobs.worker_name_of(settings.worker_name))
    server.rtc_session(run_job, agent_name=name, on_session_end=end_job)
    return server


def overflow_server(settings: Settings) -> AgentServer:
    """The overflow's AgentServer, under <fleet>/overflow, on any free port, always open."""
    key, secret = key_pair(settings)
    preload_plugins()
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


# The heartbeat goes on until the drain is over: a worker that drains still holds calls, and the
# gateway forgets one it does not hear.
async def run_worker(settings: Settings) -> int:
    """Run the worker until it is told to stop or cordoned; the exit it leaves with."""
    load = jobs.Load(settings.max_jobs)
    server = worker_server(settings, load)
    gateway = _gateway(settings)
    minute = jobs.LastMinute()
    measures = jobs.measures_path(settings.fleet, settings.worker_http_port)
    hearing = await jobs.listen_for_jobs(measures, minute)
    worker = jobs.worker_name_of(settings.worker_name)
    beats = jobs.Heartbeats(server, gateway, minute, load, fleet_name=settings.fleet, worker=worker)
    loops = Loops()
    # A beat counts the calls in livekit's pool of processes, which `run` makes: the first beat waits
    # for the server to start (in production every worker's first beat failed on 2026-11-12).
    server.on("worker_started", lambda: loops.start(jobs_tasks.beat.bind(beats)))  # pyright: ignore[reportUnknownMemberType]
    stopping = stop_on_a_signal()
    running = asyncio.create_task(server.run())
    ready = asyncio.create_task(jobs.announce_ready(beats, settings.notify_socket))
    waits = {running, asyncio.create_task(stopping.wait()), asyncio.create_task(beats.leave.wait())}
    await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    try:
        await server.drain(DRAIN_S)
    except TimeoutError:
        # livekit raises when the drain runs out; the close is what shuts and seals the calls left.
        logger.warning(STILL_UP, len(server.active_jobs), DRAIN_S)
    await server.aclose()
    await loops.stop()
    for task in (*waits, ready):
        task.cancel()
    hearing.close()
    measures.unlink(missing_ok=True)
    await gateway.aclose()
    return jobs.CORDONED_EXIT if beats.cordoned else 0


async def run_overflow(settings: Settings) -> int:
    """Run the overflow until told to stop: the gateway sends it calls no worker has a place for."""
    server = overflow_server(settings)
    stopping = stop_on_a_signal()
    running = asyncio.create_task(server.run())
    await asyncio.wait({running, asyncio.create_task(stopping.wait())}, return_when=asyncio.FIRST_COMPLETED)
    await server.aclose()
    return 0


# Every plugin imported in the worker's own process is one livekit lists in its forkserver's
# preload: imported once there, inherited by each call's process. Imported in the call's process
# instead, they held its loop 3-5 s on an idle box, up to 70 s on a loaded one, while the caller
# waited (the load lab, 2026-10-01).
def preload_plugins() -> None:
    """Import every installed vendor's plugin in this process, before livekit forks its jobs' from it."""
    providers.list_vendors()


def _always_open(_server: AgentServer) -> float:
    return OPEN


def _gateway(settings: Settings) -> jobs.GatewayClient:
    key = None if settings.worker_key is None else settings.worker_key.get_secret_value()
    return jobs.open_gateway(settings.gateway_url, key)


# What `prewarm` kept for this process, under its one name.
def _get_warmed(proc: JobProcess) -> jobs.Warmed:
    warmed: jobs.Warmed = proc.userdata[WARMED]
    return warmed
