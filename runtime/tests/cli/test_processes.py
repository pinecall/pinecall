"""The gateway as a process: `pinecall-runtime gateway` serves, and a stop ends it cleanly."""

import asyncio
import os
import signal
import socket
import sys

import httpx
import pytest

from tests.conftest import needs_the_database

UP_WITHIN_S = 60.0
DOWN_WITHIN_S = 30.0


def _a_free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@needs_the_database
@pytest.mark.usefixtures("engine")
async def test_the_gateway_serves_and_stops_on_a_terminate() -> None:
    """Started as the operator starts it, it answers its docs; SIGTERM ends it after its shutdown completes."""
    port = _a_free_port()
    environ = {**os.environ, "PINECALL_GATEWAY_LISTEN": f"127.0.0.1:{port}"}
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "runtime.cli", "gateway", env=environ, stderr=asyncio.subprocess.PIPE
    )
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http:
            async with asyncio.timeout(UP_WITHIN_S):
                while True:
                    try:
                        if (await http.get("/v1/docs")).is_success:
                            break
                    except httpx.TransportError:
                        assert process.returncode is None, "the gateway ended before it served"
                    await asyncio.sleep(0.2)
        process.send_signal(signal.SIGTERM)
        async with asyncio.timeout(DOWN_WITHIN_S):
            _, said = await process.communicate()
        # uvicorn raises the signal it caught again once it has shut down, so the process ends by it.
        assert process.returncode == -signal.SIGTERM, said.decode()
        assert "Application shutdown complete" in said.decode()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
