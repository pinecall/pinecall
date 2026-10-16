"""A call's recording as a player reads it: plain, or sealed and opened a range at a time."""

import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import FileResponse, StreamingResponse

from pinecall_runtime.calls import recordings
from pinecall_runtime.calls.auth import CallReaderDep, TheServing, check_readable, record_read
from pinecall_runtime.calls.service import lists
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import ReadKind
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit.sealed_audio import on_disk
from pinecall_runtime.postgres import Session

router = APIRouter()

NOT_RECORDED = "call {call} kept no recording"
NOT_HERE = "the recording of {call} is at {path} on the box that took the call, not on this one"


# From the bucket once the worker moved it there, else the file the recorder wrote on this disk;
# a sealed one is opened by the call's own key, the range asked for and no more.
@router.get("/v1/calls/{call}/recording", response_model=None)
async def recording(
    call: str,
    reader: CallReaderDep,
    serving: TheServing,
    session: Session,
    byte_range: Annotated[str | None, Header(alias="range")] = None,
) -> FileResponse | StreamingResponse:
    """The call's audio, with byte ranges so a player can seek."""
    await check_readable(session, serving, reader, call)
    await record_read(session, reader, call, ReadKind.recording)
    state = await serving.logs.reading(call).snapshot()
    entries = await serving.logs.store.whole(call)
    summary = next((item for item in reversed(entries) if item.type == "call.summary"), None)
    pointer = None if summary is None else summary.data.get("recording")
    if state.seq == 0 or not isinstance(pointer, str) or not pointer:
        raise NotFound(NOT_RECORDED.format(call=call))
    root = Path(serving.handles.settings.recordings_root)
    path = await asyncio.to_thread(recordings.kept_on_disk, root, call, pointer)
    if path is None:
        raise NotFound(NOT_RECORDED.format(call=call))
    kept = await lists.head_of_call(session, call)
    if kept is not None and kept.scope is not None:
        fetched = await _fetched(session, serving, kept.scope.org, call, path, byte_range)
        if fetched is not None:
            headers = {**fetched.headers, "content-disposition": f'attachment; filename="{call}.ogg"'}
            return StreamingResponse(fetched.body, status_code=fetched.status, headers=headers, media_type="audio/ogg")
    if path.name == recordings.SEALED_FILE or not await asyncio.to_thread(path.is_file):
        raise NotFound(NOT_HERE.format(call=call, path=pointer))
    return FileResponse(path, media_type="audio/ogg", filename=f"{call}.ogg")


# A sealed recording is in the bucket, or on this disk where its upload failed; a plain one is
# the bucket's to answer, and a file on this disk is served as a file.
async def _fetched(
    session: Session, serving: Serving, org: str, call: str, path: Path, byte_range: str | None
) -> recordings.Fetched | None:
    stored = recordings.recordings_of(serving.handles.settings, serving.handles.http)
    if path.name != recordings.SEALED_FILE:
        return await stored.fetch(org, call, byte_range)
    key = await compliance.recording_key_of(session, serving.handles.vault, call)
    kept = await stored.sealed(org, call) or await on_disk(call, path)
    return None if key is None or kept is None else recordings.served_sealed(kept, key, byte_range)
