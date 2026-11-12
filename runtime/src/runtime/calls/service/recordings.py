"""A call's recording as a player reads it: found by what its summary says was kept, plain or sealed and opened."""

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.calls.recordings import SEALED_FILE, Ranged, Recordings, name_of, open_sealed
from runtime.calls.repository.entries import EntryRepository
from runtime.calls.service.reading import Readable
from runtime.compliance import service as compliance
from runtime.exceptions import NotFound
from runtime.kit.crypto import Vault

SUMMARY = "call.summary"


# From the bucket once the worker moved it there, else the file the recorder wrote on this disk;
# a sealed one is opened by the call's own key, the range asked for and no more. A player that
# seeks asks once per range: the summary is found by one row of the log's key, where until 2026-11
# every range read the whole log and folded its state for the pointer.
async def recording_of(
    session: AsyncSession, recordings: Recordings, vault: Vault, readable: Readable, byte_range: str | None
) -> Ranged:
    """The call's audio, the range asked for when one is; refused for a call that kept none, or keeps it elsewhere."""
    call, head = readable.call, readable.head
    summary = await EntryRepository(session).find_newest(call, SUMMARY)
    pointer = None if summary is None else summary.data.get("recording")
    name = name_of(pointer) if isinstance(pointer, str) and pointer else None
    if name is None or pointer is None or head is None or head.scope is None:
        raise NotFound(f"call {call} kept no recording")
    found = await _fetch(session, recordings, vault, head.scope.org, call, name, byte_range)
    if found is None:
        raise NotFound(f"the recording of {call} is at {pointer} on the box that took the call, not on this one")
    return found


# A sealed recording is in the bucket, or on this disk where its upload failed; so is a plain one.
async def _fetch(
    session: AsyncSession, recordings: Recordings, vault: Vault, org: str, call: str, name: str, byte_range: str | None
) -> Ranged | None:
    if name != SEALED_FILE:
        return await recordings.fetch(org, call, byte_range)
    key = await compliance.recording_key_of(session, vault, call)
    sealed = await recordings.find_sealed(org, call)
    return None if key is None or sealed is None else open_sealed(sealed, key, byte_range)
