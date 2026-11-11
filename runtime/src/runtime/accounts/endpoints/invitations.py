"""An invitation accepted: the password typed, the member active, their first key."""

from fastapi import APIRouter

from runtime.accounts import schemas
from runtime.accounts.auth import MinPassword, TheKeyCache
from runtime.accounts.service import invitations
from runtime.postgres import Session

router = APIRouter()


@router.post("/v1/invitations/{token}")
async def accept_invitation(
    token: str, body: schemas.AcceptInvitation, shortest: MinPassword, cache: TheKeyCache, session: Session
) -> schemas.FirstKey:
    """Type the password: the member is active, and here is their first key."""
    first = await invitations.accept_invitation(session, cache, token, body.password, shortest, device=body.device)
    return schemas.FirstKey.of(first)
