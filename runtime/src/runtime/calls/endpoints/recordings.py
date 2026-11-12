"""A call's recording as a player reads it: plain, or sealed and opened a range at a time."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from runtime.calls.auth import TheRecordedCall, TheRecordings
from runtime.calls.recordings import Ranged
from runtime.calls.service import recordings
from runtime.handles import TheVault
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/calls/{call}/recording", response_model=None)
async def recording(
    readable: TheRecordedCall,
    kept: TheRecordings,
    vault: TheVault,
    session: Session,
    byte_range: Annotated[str | None, Header(alias="range")] = None,
) -> StreamingResponse:
    """The call's audio, with byte ranges so a player can seek."""
    found = await recordings.recording_of(session, kept, vault, readable, byte_range)
    return _answer(readable.call, found)


# The whole is 200, a range of it 206, and a range that starts past its end 416 with its size.
def _answer(call: str, found: Ranged) -> StreamingResponse:
    headers = {"content-disposition": f'attachment; filename="{call}.ogg"'}
    if not found.satisfiable:
        status = HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE
        headers |= {"content-range": f"bytes */{found.size}"}
    else:
        status = HTTPStatus.OK if found.span is None else HTTPStatus.PARTIAL_CONTENT
        headers |= {"accept-ranges": "bytes", "content-length": str(found.length)}
    if found.satisfiable and found.span is not None:
        headers |= {"content-range": f"bytes {found.span.first}-{found.span.last}/{found.size}"}
    return StreamingResponse(found.body, status_code=status, headers=headers, media_type="audio/ogg")
