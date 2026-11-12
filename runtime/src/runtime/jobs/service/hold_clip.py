"""The clip a call plays while a tool runs: the runtime's melody, or the org's own, fetched once per box."""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from runtime.actor import Scope
from runtime.enums import HoldPlayed
from runtime.exceptions import UpstreamError
from runtime.jobs.service.client import GatewayClient
from runtime.session import service as session
from runtime.wire.worker import HoldAudio

logger = logging.getLogger(__name__)

# Clips are cached by their hash: each is fetched once per box.
HOLD_CACHE = Path(tempfile.gettempdir()) / "pinecall-hold"


async def find_hold_clip(gateway: GatewayClient, agent: str, scope: Scope, held: HoldAudio) -> Path | None:
    """The clip the agent plays, on this disk: the runtime's, or the org's own from the box's cache; None for none."""
    if held.played is HoldPlayed.off:
        return None
    if held.played is HoldPlayed.default:
        return session.runtime_melody()
    if held.sha256 is None:
        return None
    cached = HOLD_CACHE / f"{held.sha256}.ogg"
    if not cached.is_file():
        try:
            audio = await gateway.get_hold_clip(agent, scope)
        except UpstreamError:
            logger.warning("the hold clip of %s could not be fetched: the call plays none", agent)
            return None
        await asyncio.to_thread(_write_beside, cached, audio)
    return cached


# Written beside and renamed, so a job reading the cache never reads half a file.
def _write_beside(cached: Path, audio: bytes) -> None:
    cached.parent.mkdir(parents=True, exist_ok=True)
    part = cached.with_suffix(f".{os.getpid()}.part")
    part.write_bytes(audio)
    part.replace(cached)
