"""`python -m pinecall.serve`: what the CLI runs, run the way the CLI runs it."""

import asyncio
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from tests.fakes.gateway import KEY, FakeGateway
from tests.fakes.project import written


def test_the_module_runs_the_entry_with_its_argv_and_exits_with_its_status(tmp_path: Path) -> None:
    file = written(tmp_path)
    ran = subprocess.run(
        [
            sys.executable,
            "-m",
            "pinecall.serve",
            "prompt",
            "--file",
            str(file),
            "--slug",
            "recepcion",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.rstrip().endswith("Pide el nombre.")
    usage = subprocess.run(
        [sys.executable, "-m", "pinecall.serve"], capture_output=True, text=True, check=False
    )
    assert usage.returncode == 2


async def serving(gateway: FakeGateway, file: Path) -> asyncio.subprocess.Process:
    env = os.environ | {"PINECALL_URL": gateway.url, "PINECALL_KEY": KEY}
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pinecall.serve",
        "start",
        "--file",
        str(file),
        "--slug",
        "recepcion",
        "--events",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    assert child.stdout is not None
    first = json.loads(await asyncio.wait_for(child.stdout.readline(), 10))
    assert (first["type"], first["agent"]) == ("agent.registered", "recepcion")
    return child


async def test_a_sigterm_drains_the_process_and_it_leaves_with_0(
    gateway: FakeGateway, tmp_path: Path
) -> None:
    child = await serving(gateway, written(tmp_path))
    child.send_signal(signal.SIGTERM)
    # The drain's line is read before stdin is closed: `communicate` closes it at once, and a stdin
    # that ends is the other reason to leave, which drains without a line.
    assert child.stderr is not None
    said = await asyncio.wait_for(child.stderr.readline(), 10)
    await asyncio.wait_for(child.communicate(), 10)
    assert child.returncode == 0
    assert said.decode().strip() == "draining · 1 live call handed over"
    assert len(gateway.commands_of("agent.drain")) == 1


async def test_the_cli_that_started_it_gone_its_stdin_closes_and_it_leaves(
    gateway: FakeGateway, tmp_path: Path
) -> None:
    child = await serving(gateway, written(tmp_path))
    assert child.stdin is not None
    child.stdin.close()
    await asyncio.wait_for(child.wait(), 10)
    assert child.returncode == 0
    assert len(gateway.commands_of("agent.drain")) == 1


async def test_a_registration_the_gateway_refuses_is_its_sentence_and_2_not_a_traceback(
    tmp_path: Path,
) -> None:
    gateway = FakeGateway(taken=frozenset({"recepcion"}))
    await gateway.start()
    env = os.environ | {"PINECALL_URL": gateway.url, "PINECALL_KEY": KEY}
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pinecall.serve",
        "start",
        "--file",
        str(written(tmp_path)),
        "--slug",
        "recepcion",
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    _, err = await asyncio.wait_for(child.communicate(), 10)
    assert child.returncode == 2
    assert err.decode().strip() == "refused: recepcion is taken"
    await gateway.close()
