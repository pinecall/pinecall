"""A process told to stop: the event SIGTERM and SIGINT set."""

import asyncio
import signal


# Asked on the running loop, once per process: until 2026-11 the worker and the runner each wrote it.
def stop_on_a_signal() -> asyncio.Event:
    """The event set when the process is told to stop, by its supervisor or at a terminal."""
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(stop, stopping.set)
    return stopping
