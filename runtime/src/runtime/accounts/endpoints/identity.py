"""Who a key is: whose it is, the env its request acts in, what it opens, and the person's own account."""

from fastapi import APIRouter

from runtime.accounts import schemas
from runtime.accounts.auth import AnyKey, PersonKey, TheKeyCache, TheOwnSeat
from runtime.accounts.service import keys, members
from runtime.accounts.service.actor import identify
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/whoami")
async def whoami(actor: AnyKey, session: Session) -> schemas.Whoami:
    """Whose key this is, the env this request acts in, and what the key opens."""
    return schemas.Whoami.of(await identify(session, actor))


@router.get("/v1/me")
async def read_me(seat: TheOwnSeat) -> schemas.Me:
    """The person behind the key: their name and address, their role here, whether a password opens their account."""
    return schemas.Me.of(seat)


@router.patch("/v1/me")
async def change_me(body: schemas.ChangeMe, seat: TheOwnSeat, cache: TheKeyCache, session: Session) -> schemas.Me:
    """Change the name this org calls you by."""
    return schemas.Me.of(await members.rename_member(session, cache, seat, body.name))


@router.get("/v1/me/keys")
async def list_sign_ins(actor: PersonKey, session: Session) -> list[schemas.SignInRow]:
    """The keys your own sign-ins to this org left, the latest used first, and which one this request came with."""
    return [schemas.SignInRow.of(one) for one in await keys.list_sign_ins(session, actor)]
