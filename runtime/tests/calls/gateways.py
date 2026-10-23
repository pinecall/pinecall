"""A second gateway of the same box, served beside the suite's own, for what happens between two."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import uvicorn

from pinecall_runtime.app import create_app
from tests.conftest import Gateway


# On the same database and the same Redis, as production's two gateways are one box: a call
# opened on one is read, sealed and handed on from the other.
@asynccontextmanager
async def a_second_gateway() -> AsyncGenerator[Gateway]:
    """Another gateway of this run's box, on a free port, stopped when the block ends."""
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        if serving.done():
            serving.result()
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    try:
        async with httpx.AsyncClient(base_url=url, timeout=10.0) as http:
            yield Gateway(url, http, app)
    finally:
        server.should_exit = True
        await serving
