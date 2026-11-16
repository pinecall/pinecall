"""The runtime's processes as children of `setup` and `local up`: the gateway heard first, their lines told apart."""

import os
import signal
import subprocess
import sys
import threading
import time
from typing import IO
from urllib.parse import urlsplit

from runtime.cli.command import FOUND_WRONG, OK
from runtime.cli.output import Printer
from runtime.providers.service import machine

# The runner of what `pinecall deploy` sends a runtime of one's own.
RUNNER = ["runner", "start"]
GATEWAY = ["gateway"]
WORKER = ["worker", "start"]
# The setting that says where this machine's gateway answers: the worker and the runner ask it there.
GATEWAY_AT = "PINECALL_GATEWAY_URL"
# How long the others wait for the gateway to listen; past it they start all the same and say what they find.
GATEWAY_WITHIN_S = 60.0
ASKED_EVERY_S = 0.2


# The gateway is what the other two ask, so it is started alone and heard on its port before they are:
# until 2026-11-16 the three started at once, and the runner's first beats found nobody and said so,
# three warnings under "Running." at every start.
def run_children(out: Printer, values: dict[str, str], *verbs: list[str]) -> int:
    """Run the verbs as child processes of this package on the machine's settings until Ctrl-C; 1 when one failed."""
    children: list[subprocess.Popen[str]] = []
    readers: list[threading.Thread] = []
    stopping = threading.Event()

    def stop(_signal: int, _frame: object) -> None:
        stopping.set()
        for child in children:
            child.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    out.line("Running. Ctrl-C stops it; `pinecall-runtime setup` starts it again.")
    for verb in verbs:
        if stopping.is_set():
            break
        child = subprocess.Popen(
            [sys.executable, "-m", "runtime.cli", *verb],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, **values},
        )
        children.append(child)
        readers.append(threading.Thread(target=_relay, args=(child.stdout, verb[0]), daemon=True))
        readers[-1].start()
        if verb == GATEWAY:
            _wait_for_the_gateway(child, values, stopping)
    codes = [child.wait() for child in children]
    for reader in readers:
        reader.join(timeout=1)
    return OK if all(code in (0, -signal.SIGTERM) for code in codes) else FOUND_WRONG


# A gateway that ended, a Ctrl-C and the deadline each end the wait: the rest is the caller's to say.
def _wait_for_the_gateway(gateway: subprocess.Popen[str], values: dict[str, str], stopping: threading.Event) -> None:
    port = urlsplit(values.get(GATEWAY_AT, "")).port
    if port is None:
        return
    deadline = time.monotonic() + GATEWAY_WITHIN_S
    while gateway.poll() is None and not stopping.is_set() and time.monotonic() < deadline:
        if machine.answers(port):
            return
        time.sleep(ASKED_EVERY_S)


def _relay(out: IO[str] | None, prefix: str) -> None:
    if out is None:
        return
    for line in out:
        sys.stdout.write(f"{prefix:<8}| {line}")
        sys.stdout.flush()
