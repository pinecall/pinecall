"""A call's recording once its session closed it: whether it was written, sealed, and kept where the box keeps them."""

import asyncio
import logging
from pathlib import Path

from runtime.calls.recordings import SEALED_FILE, Recordings
from runtime.exceptions import UpstreamError
from runtime.jobs.service.call_client import CallClient
from runtime.jobs.service.client import LONGEST_WAIT_S
from runtime.kit.retry import keep_asking
from runtime.kit.sealed_file import seal_file

logger = logging.getLogger(__name__)

DROPPED = "the recording of %s is dropped, never kept unsealed: %s"

# How long a gateway that is away is asked again for the key; one that answered a refusal is not asked twice.
KEY_WITHIN_S = 13.0


# The session closed its recorder before it seals: the seal points at a whole file. A call that
# ended before its session started recording has no file, and the seal names none.
async def keep_recording(
    store: Recordings, link: CallClient, org: str, audio: Path, *, key_within_s: float = KEY_WITHIN_S
) -> str | None:
    """Seal the call's written recording and move it where the box keeps it; the file the seal names, or None."""
    if not await asyncio.to_thread(has_audio, audio):
        return None
    sealed = await _seal_recording(link, audio, key_within_s)
    if sealed is None:
        return None
    try:
        await store.store(org, link.call, sealed)
    except UpstreamError:
        logger.warning("the recording of %s stays on this disk", link.call, exc_info=True)
    return str(sealed)


def has_audio(audio: Path) -> bool:
    """Whether the session wrote the call's audio."""
    return audio.is_file() and audio.stat().st_size > 0


# Sealed on this disk before it goes anywhere, under a key the gateway keeps sealed for the call.
# No recording is ever kept as it was written: one the worker cannot seal is removed and the seal
# names none, as a call nobody recorded (docs/security/private-values.md).
async def _seal_recording(link: CallClient, audio: Path, within_s: float) -> Path | None:
    sealed = audio.with_name(SEALED_FILE)
    try:
        key = await keep_asking(
            link.recording_key,
            within_s=within_s,
            what=f"the recording key of {link.call}",
            longest_s=LONGEST_WAIT_S,
        )
    except UpstreamError as refused:
        logger.error(DROPPED, link.call, f"the gateway gave no key: {refused}")
        await asyncio.to_thread(_remove_files, audio, sealed)
        return None
    try:
        await asyncio.to_thread(seal_file, audio, sealed, key)
    except OSError:
        logger.exception(DROPPED, link.call, "the sealed file could not be written")
        await asyncio.to_thread(_remove_files, audio, sealed)
        return None
    return sealed


def _remove_files(*files: Path) -> None:
    for file in files:
        file.unlink(missing_ok=True)
