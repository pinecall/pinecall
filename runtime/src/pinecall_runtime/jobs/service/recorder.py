"""A call's recording once its session closed it: whether it was written, sealed, and stored."""

import asyncio
import logging
from http import HTTPStatus
from pathlib import Path

import httpx

from pinecall_runtime.calls import service as calls
from pinecall_runtime.config import Settings
from pinecall_runtime.exceptions import GatewayUnavailable, UpstreamError
from pinecall_runtime.jobs.service.client import GatewayClient
from pinecall_runtime.kit.sealed_audio import seal_file

logger = logging.getLogger(__name__)

DROPPED = "the recording of %s is dropped, never kept unsealed: %s"

# A gateway that is away is asked again after each wait; one that answered a refusal is not.
KEY_WAITS_S = (1.0, 3.0, 9.0)


# A call that ended before its session started recording has no file, and the seal names none.
def has_audio(audio: Path) -> bool:
    """Whether the session wrote the call's audio."""
    return audio.is_file() and audio.stat().st_size > 0


# The seal waits for this: it names the file, and the gateway finds it wherever it went.
async def store_recording(settings: Settings, gateway: GatewayClient, org: str, call: str, audio: Path) -> Path | None:
    """Seal a written recording and move it where the box keeps it; the file the seal names."""
    sealed = await _seal_recording(gateway, call, audio)
    if sealed is None:
        return None
    async with httpx.AsyncClient() as http:
        try:
            await calls.recordings_of(settings, http).store(org, call, sealed)
        except UpstreamError:
            logger.warning("the recording of %s stays on this disk", call, exc_info=True)
    return sealed


# Sealed on this disk before it goes anywhere, under a key the gateway keeps sealed for the call.
# No recording is ever kept as it was written: one the worker cannot seal is removed and the seal
# names none, as a call nobody recorded (docs/security/private-values.md).
async def _seal_recording(gateway: GatewayClient, call: str, audio: Path) -> Path | None:
    key = await _key_for(gateway, call)
    sealed = audio.with_name(calls.SEALED_FILE)
    if key is None:
        logger.error(DROPPED, call, "the gateway gave no key")
        await asyncio.to_thread(_remove_files, audio, sealed)
        return None
    try:
        await asyncio.to_thread(seal_file, audio, sealed, key)
    except OSError:
        logger.exception(DROPPED, call, "the sealed file could not be written")
        await asyncio.to_thread(_remove_files, audio, sealed)
        return None
    return sealed


async def _key_for(gateway: GatewayClient, call: str) -> bytes | None:
    for wait_s in (*KEY_WAITS_S, None):
        try:
            return await gateway.recording_key(call)
        except GatewayUnavailable as refused:
            away = refused.answered is None or refused.answered >= HTTPStatus.INTERNAL_SERVER_ERROR
            if not away or wait_s is None:
                logger.warning("no key for the recording of %s", call, exc_info=True)
                return None
            await asyncio.sleep(wait_s)
    return None


def _remove_files(*files: Path) -> None:
    for file in files:
        file.unlink(missing_ok=True)
