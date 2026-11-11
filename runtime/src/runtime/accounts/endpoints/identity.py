"""Who a key is: whose it is, the env its request acts in, and what it opens."""

from fastapi import APIRouter

from runtime.accounts import schemas
from runtime.accounts.auth import AnyKey
from runtime.accounts.service.actor import identify
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/whoami")
async def whoami(actor: AnyKey, session: Session) -> schemas.Whoami:
    """Whose key this is, the env this request acts in, and what the key opens."""
    return schemas.Whoami.of(await identify(session, actor))
