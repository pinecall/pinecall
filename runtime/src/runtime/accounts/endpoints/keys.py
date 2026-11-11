"""The org's keys: listed, a server's minted, one revoked."""

from fastapi import APIRouter

from runtime.accounts import schemas
from runtime.accounts.auth import AnyKey, PersonsAppKey, TheKeyCache, ThePerson
from runtime.accounts.service import keys
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/keys")
async def list_keys(actor: AnyKey, session: Session) -> list[schemas.KeyRow]:
    """The org's keys this key may see: every server's, your own person keys, or every one with `keys`."""
    return [schemas.KeyRow.of(key) for key in await keys.list_keys_visible_to(session, actor)]


@router.post("/v1/keys")
async def create_key(
    body: schemas.CreateKey, actor: PersonsAppKey, person: ThePerson, session: Session
) -> schemas.KeyIssued:
    """A server's token for the org in one env; the secret is in this answer and never again."""
    issued = await keys.issue_server_key(
        session, person, actor.org, body.env, label=body.label, scopes=body.scopes, expires_at=body.expires_at
    )
    return schemas.KeyIssued.of(issued)


@router.post("/v1/keys/{fingerprint}/revoke")
async def revoke_key(fingerprint: str, actor: AnyKey, cache: TheKeyCache, session: Session) -> schemas.KeyRevoked:
    """Stop one of the org's keys from the next request on; a POST, so the row stays for the log."""
    await keys.revoke_key(session, cache, actor, fingerprint)
    return schemas.KeyRevoked(fingerprint=fingerprint, revoked=True)
