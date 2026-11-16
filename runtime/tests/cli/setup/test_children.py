"""The runtime's processes as `setup` starts them: the gateway alone first, the others once it listens."""

import signal
import socket
import subprocess
import threading

import pytest

from runtime.cli.command import FOUND_WRONG, OK
from runtime.cli.output import Printer
from runtime.cli.setup import children
from runtime.providers.service import machine


class AChild:
    """A process that never writes and ends with the code it was given, when it is waited for."""

    stdout = None

    def __init__(self, ends_with: int | None = None) -> None:
        """Still running, unless it ended already."""
        self.ended = ends_with

    def poll(self) -> int | None:
        """Its exit, None while it runs."""
        return self.ended

    def wait(self) -> int:
        """Its exit."""
        return self.ended or 0

    def terminate(self) -> None:
        """Nothing to stop."""


def no_handler(_number: int, _handler: object) -> None:
    """The test's own process keeps its signals."""


def a_port_nobody_answers() -> tuple[socket.socket, int]:
    """A loopback port bound and not listened on: a connection to it is refused until `listen`."""
    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    port: int = held.getsockname()[1]
    return held, port


def test_the_gateway_is_heard_on_its_port_before_the_others_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """Started together, the runner's first beats found no gateway: the worker and the runner start once it answers."""
    held, port = a_port_nobody_answers()
    started: list[tuple[str, bool]] = []

    def start(command: list[str], **_how: object) -> AChild:
        verb = command[3]
        started.append((verb, machine.answers(port)))
        if verb == "gateway":
            threading.Timer(0.3, held.listen).start()
        return AChild()

    monkeypatch.setattr(subprocess, "Popen", start)
    monkeypatch.setattr(signal, "signal", no_handler)
    values = {children.GATEWAY_AT: f"http://127.0.0.1:{port}"}
    with held:
        ran = children.run_children(Printer(as_json=False), values, children.GATEWAY, children.WORKER, children.RUNNER)
    assert ran == OK
    assert started == [("gateway", False), ("worker", True), ("runner", True)]


def test_a_gateway_that_ended_does_not_hold_the_others_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """A gateway that died before it listened is not waited for: the others start, and the run says it failed."""
    held, port = a_port_nobody_answers()
    started: list[str] = []

    def start(command: list[str], **_how: object) -> AChild:
        started.append(command[3])
        return AChild(ends_with=1 if command[3] == "gateway" else None)

    monkeypatch.setattr(subprocess, "Popen", start)
    monkeypatch.setattr(signal, "signal", no_handler)
    with held:
        ran = children.run_children(
            Printer(as_json=False), {children.GATEWAY_AT: f"http://127.0.0.1:{port}"}, children.GATEWAY, children.RUNNER
        )
    assert (ran, started) == (FOUND_WRONG, ["gateway", "runner"])
