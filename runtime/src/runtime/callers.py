"""The callers process: the callers of spoken simulations claimed off their rows and played, and the service of them."""

import asyncio
import logging
import os
import sys
from contextlib import AsyncExitStack

from livekit.agents.utils import http_context

from runtime import builders
from runtime.config import Settings
from runtime.evals import tasks as evals_tasks
from runtime.evals.parts import CallerParts
from runtime.fleet.service.offers import Offering
from runtime.fleet.service.roster import Roster
from runtime.handles import Handles
from runtime.kit.loops import Loops
from runtime.kit.signals import stop_on_a_signal
from runtime.providers.service import plugins

logger = logging.getLogger(__name__)

# A caller holds no connection while it is on the line: it reads its call's log a few times a second
# and writes a handful of rows as it starts and ends. One connection a caller is more than they use
# together, and every process of the service has a pool: eight processes of ten connections each, a
# gateway's own number, would be most of what a server's Postgres takes.
A_CONNECTION_A_CALLER = 1

# What the service gives its processes to stop, past what each gives its calls: the time to say how it
# left each one.
A_PROCESS_STOPS_WITHIN_S = evals_tasks.CALLERS_DRAIN_S + 30.0
# A process that ends on its own is started again, after this long: one that cannot start is not spun.
STARTED_AGAIN_AFTER_S = 5.0


# One Python loop, with nothing on it but the callers it plays. Told to stop, it claims no other and
# ends when the calls it has do, eleven minutes at most; what it could not finish says so on its row.
async def run_callers(settings: Settings) -> int:
    """Play simulated callers until told to stop; the exit it leaves with."""
    stopping = stop_on_a_signal()
    # Every vendor's plugin imported before the first caller: imported at the first voice instead, they
    # held the loop for seconds while a caller's frames waited (`processes.gateway` says it of requests).
    plugins.list_vendors()
    async with AsyncExitStack() as stack, http_context.open():
        pool = max(2, settings.callers_per_process * A_CONNECTION_A_CALLER)
        handles = await builders.open_connections(settings, stack, pool=pool)
        parts = await build_caller_parts(handles, stack)
        callers = builders.build_callers(settings, parts)
        loops = Loops()
        loops.start(evals_tasks.claim_callers.bind(callers))
        loops.start(evals_tasks.say_callers.bind(callers))
        loops.start(evals_tasks.watch_the_clock.bind(callers))
        logger.info("%s plays simulated callers, %d at once", callers.name, settings.callers_per_process)
        await stopping.wait()
        logger.info("%s was told to stop with %d callers on the line", callers.name, callers.playing)
        await callers.stop(evals_tasks.CALLERS_DRAIN_S)
        await loops.stop()
    return 0


# A callers process serves no agent, answers no request and sweeps no fleet: it has the database, the
# log's engine, the roster of workers (heard on the signal, to take a seat and ring it) and what signs
# its callers into their rooms. The gateways sweep the offers; this one only makes them.
async def build_caller_parts(handles: Handles, stack: AsyncExitStack) -> CallerParts:
    """What a callers process plays its callers with, the roster listening."""
    _writer, store, _relay, _feeds, logs = builders.build_log_engine(
        handles.settings, handles.sessions, handles.signal, stack
    )
    roster = Roster(handles.signal)
    await roster.start()
    stack.push_async_callback(roster.close)
    return CallerParts(
        settings=handles.settings,
        vault=handles.vault,
        servers=handles.servers,
        names=builders.read_sip_names(handles.settings),
        sessions=handles.sessions,
        store=store,
        logs=logs,
        signer=builders.build_signer(handles.settings),
        offering=Offering(handles.sessions, handles.servers, roster),
        roster=roster,
    )


def count_processes(settings: Settings) -> int:
    """How many processes the service runs: as the settings say, else half the cores it is given, at least one."""
    return settings.caller_processes or max(1, (os.process_cpu_count() or 2) // 2)


# The service is its processes and nothing else: each is started with the service's own command and
# environment, started again when it ends on its own, and told to stop when the service is. It ends
# when the last of them has, so whoever stops the service waits for the calls its processes play.
async def run_callers_service(settings: Settings) -> int:
    """Run the callers' processes until told to stop, then wait for each to end its calls."""
    stopping = stop_on_a_signal()
    command = [sys.executable, "-m", "runtime.cli", "callers", "play"]
    wanted = count_processes(settings)
    logger.info("the callers service runs %d processes, %d callers each", wanted, settings.callers_per_process)
    running = [await asyncio.create_subprocess_exec(*command) for _ in range(wanted)]
    stopped = asyncio.create_task(stopping.wait())
    while not stopping.is_set():
        ended = {asyncio.create_task(process.wait()): at for at, process in enumerate(running)}
        done, pending = await asyncio.wait({stopped, *ended}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending - {stopped}:
            task.cancel()
        if stopping.is_set():
            break
        await asyncio.sleep(STARTED_AGAIN_AFTER_S)
        for task in done - {stopped}:
            logger.warning("a callers process ended on its own (exit %s): started again", task.result())
            running[ended[task]] = await asyncio.create_subprocess_exec(*command)
    for process in running:
        if process.returncode is None:
            process.terminate()
    try:
        async with asyncio.timeout(A_PROCESS_STOPS_WITHIN_S):
            await asyncio.gather(*(process.wait() for process in running))
    except TimeoutError:
        for process in running:
            if process.returncode is None:
                process.kill()
    return 0
