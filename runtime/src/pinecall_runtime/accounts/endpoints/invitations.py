"""An invitation accepted: the password typed, the member active, their first key."""

from fastapi import APIRouter

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import (
    MinPassword,
)
from pinecall_runtime.accounts.service import keys, members
from pinecall_runtime.exceptions import (
    NotFound,
)
from pinecall_runtime.postgres import Session

router = APIRouter()

NO_INVITATION = "no open invitation answers to that token: it was used, it expired, or it never existed"


@router.post("/v1/invitations/{token}")
async def accept_invitation(
    token: str, body: schemas.AcceptInvitation, shortest: MinPassword, session: Session
) -> schemas.FirstKey:
    """Type the password: the member is active, and here is their first key."""
    members.check_password(body.password, shortest)
    member = await members.accept_link(session, token, body.password, shortest)
    if member is None:
        raise NotFound(NO_INVITATION)
    key, secret = await keys.issue_person_key(session, member, label=body.device or "invitation")
    return schemas.FirstKey(**schemas.KeyIssued.minted(key, secret).model_dump(), member=schemas.MemberRow.of(member))
