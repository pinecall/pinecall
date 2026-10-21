"""A visitor's endpoints: a browser's room token, a conversation resumed, a code a caller keys, their hang-up."""

from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.calls import schemas
from pinecall_runtime.calls.auth import CallReaderDep, ReaderDep, TalkKey, TheServing, check_readable
from pinecall_runtime.calls.service import desk, visitors
from pinecall_runtime.exceptions import Forbidden
from pinecall_runtime.postgres import Session

router = APIRouter()

A_KEY_ENDS_WITH_A_VERB = (
    "a hang-up is the caller's own, said with the call's token: a key ends a call with the verb end"
)


@router.post("/v1/tokens", status_code=201)
async def mint_room_token(
    body: schemas.MintTokenRequest, actor: TalkKey, serving: TheServing, session: Session
) -> schemas.MintTokenResponse:
    """A room token for one of the key's agents: a new call, or one resumed."""
    return await visitors.mint_room_token(session, serving, actor, body)


@router.post("/v1/codes", status_code=201)
async def issue_code(
    body: schemas.IssueCodeRequest, actor: TalkKey, serving: TheServing, session: Session
) -> schemas.IssueCodeResponse:
    """Four digits for a caller to key, the number to call, and a token that asks after them."""
    return await visitors.issue_code(session, serving, actor, body)


@router.get("/v1/codes/{code}")
async def code_status(
    code: str, reader: ReaderDep, serving: TheServing, session: Session, query: Annotated[schemas.CodeQuery, Query()]
) -> schemas.CodeStatus:
    """How the code stands; with ?wait=1, held up to 25 s for a call to key it."""
    if reader.visit is None:
        raise Forbidden("this token reads another code")
    return await visitors.code_status(session, serving, reader.visit, code, wait=query.wait)


# The page says it before it leaves the room, over HTTP, which a closing tab still completes
# (`keepalive`): said on the room's data channel alone, the hang-up is lost with the seat and the
# call waits five minutes for a caller who is not coming back (tokens.md).
@router.post("/v1/calls/{call}/hangup", status_code=202)
async def hang_up(call: str, reader: CallReaderDep, serving: TheServing, session: Session) -> schemas.HangupResponse:
    """The caller hung up: the call ends now, as `caller_hung_up`; with the call's own token alone."""
    if reader.visit is None:
        raise Forbidden(A_KEY_ENDS_WITH_A_VERB)
    await check_readable(session, serving, reader, call)
    await desk.caller_hung_up(serving, call)
    return schemas.HangupResponse(call=call)
