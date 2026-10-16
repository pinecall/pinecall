"""A visitor's endpoints: a browser's room token, a conversation resumed, a code a caller keys."""

from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.calls import schemas
from pinecall_runtime.calls.auth import ReaderDep, TalkKey, TheServing
from pinecall_runtime.calls.service import visitors
from pinecall_runtime.exceptions import Forbidden
from pinecall_runtime.postgres import Session

router = APIRouter()


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
