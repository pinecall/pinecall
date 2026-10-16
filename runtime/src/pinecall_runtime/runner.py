"""The runner process: an env's hosted apps kept running as the gateway wants them."""

from pinecall_runtime.config import Settings
from pinecall_runtime.hosting import service as hosting


async def run_runner(settings: Settings) -> int:
    """Keep the env's hosted apps running until told to stop; the exit it leaves with."""
    return await hosting.run_runner(settings)
