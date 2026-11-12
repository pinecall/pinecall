"""The runtime's processes as children of `setup` and `local up`: their lines told apart, stopped together."""

import os
import signal
import subprocess
import sys
import threading
from typing import IO

from runtime.cli.command import FOUND_WRONG, OK
from runtime.cli.output import Printer

RUNNING = "Running. Ctrl-C stops it; `pinecall-runtime setup` starts it again."
# The runner of what `pinecall deploy` sends a runtime of one's own.
RUNNER = ["runner", "start"]
GATEWAY = ["gateway"]
WORKER = ["worker", "start"]


def run_children(out: Printer, values: dict[str, str], *verbs: list[str]) -> int:
    """Run the verbs as child processes of this package on the machine's settings until Ctrl-C; 1 when one failed."""
    children = [
        subprocess.Popen(
            [sys.executable, "-m", "runtime.cli", *verb],
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
