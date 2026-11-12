"""The load livekit reads of a worker: its line times the slots taken, or the machine's CPU share."""

import logging
from collections.abc import Callable
from dataclasses import fields

from livekit.agents import AgentServer
from livekit.agents.worker import ServerOptions

from runtime.exceptions import ConfigurationError
from runtime.fleet import service as fleet

logger = logging.getLogger(__name__)

NO_MEASURE = "livekit's load_fnc option no longer carries a measure of its own"
NOT_A_SLOT = "a worker holds at least one call: PINECALL_MAX_JOBS={max_jobs}"


# What LiveKit reads, on LiveKit's scale: its server offers a job under REFUSED_AT and its
# framework declines at it, so a worker that counts its calls is at REFUSED_AT with every slot
# taken. The server reads the load the worker last reported (every 2.5 s): a burst faster than
# that, on a worker's last slots, is declined by the framework and offered to no one else.
class Load:
    """The load LiveKit reads: its line times the slots taken, or the machine's CPU share."""

    def __init__(self, max_jobs: int | None, measure: Callable[[AgentServer], float] | None = None) -> None:
        """A worker nobody has dispatched to yet."""
        if max_jobs is not None and max_jobs < 1:
            raise ConfigurationError(NOT_A_SLOT.format(max_jobs=max_jobs))
        self.max_jobs = max_jobs
        self.measure = measure or livekits_measure()
        self.refused = False

    # livekit calls this from a thread of its own, every 2.5 s: the one reader that says a crossing.
    def __call__(self, server: AgentServer) -> float:
        """The load now, as livekit reads it, a crossing of its line said once each way."""
        load = self.read(server)
        is_refused = load >= fleet.REFUSED_AT
        if is_refused != self.refused:
            self.refused = is_refused
            if is_refused:
                logger.warning("load %.2f: livekit routes no job here until it falls", load)
            else:
                logger.info("load %.2f: livekit routes jobs here again", load)
        return load

    # Until 2026-11 the heartbeat read the load through `__call__`, which logs and keeps which side
    # of the line it is on: a question with an effect, asked from two threads.
    def read(self, server: AgentServer) -> float:
        """The load now, and nothing else: asked by whoever only wants the number."""
        if self.max_jobs is None:
            return self.measure(server)
        return self.at(len(server.active_jobs))

    def at(self, active: int) -> float:
        """The load of a worker holding this many calls, when its slots were measured."""
        return fleet.REFUSED_AT * active / (self.max_jobs or 1)


# livekit's own CPU average, read off its options' default rather than its private class.
def livekits_measure() -> Callable[[AgentServer], float]:
    """The load function livekit runs when given none: the machine's CPU over a few seconds."""
    (option,) = (one for one in fields(ServerOptions) if one.name == "load_fnc")
    measure = option.default
    if not callable(measure):
        raise ConfigurationError(NO_MEASURE)

    def measure_now(server: AgentServer) -> float:
        load = measure(server)
        if not isinstance(load, int | float):
            raise ConfigurationError(NO_MEASURE)
        return float(load)

    return measure_now
