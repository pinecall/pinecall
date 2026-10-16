"""The org's keys: listed, a server's minted, one revoked."""

from fastapi import APIRouter

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import (
    AnyKey,
    AppKey,
    KeyCacheDep,
    ThePerson,
)
from pinecall_runtime.accounts.service import keys, members
from pinecall_runtime.enums import Env, KeyScope
from pinecall_runtime.exceptions import (
    Forbidden,
)
from pinecall_runtime.postgres import Session

router = APIRouter()


@router.get("/v1/keys")
async def list_keys(actor: AnyKey, session: Session) -> list[schemas.KeyRow]:
    """The org's keys this key may see: every server's, your own person keys, or every one with `keys`."""
    names = {m.id: m.name for m in await members.list_members(session, actor.org)}
    subject = None if actor.person is None else actor.person.id
    return [
        schemas.KeyRow.with_names(key, names)
        for key in await keys.list_keys(session, actor.org)
        if key.subject is None or key.subject == subject or KeyScope.keys in actor.scopes
    ]


@router.post("/v1/keys")
async def create_key(body: schemas.CreateKey, actor: AppKey, person: ThePerson, session: Session) -> schemas.KeyIssued:
    """A server's token for the org in one env; the secret is in this answer and never again."""
    if body.env is Env.production and not person.opens_production:
        raise Forbidden(f"{person.name} has no production access: a production token is made by somebody who has")
    keys.check_expiry(body.expires_at)
    issue = keys.Issue(
        org=actor.org,
        env=body.env,
        scopes=keys.server_scopes(body.scopes),
        label=body.label,
        created_by=person.id,
        expires_at=body.expires_at,
    )
    key, secret = await keys.issue_key(session, issue)
    return schemas.KeyIssued.minted(key, secret)


@router.post("/v1/keys/{fingerprint}/revoke")
async def revoke_key(fingerprint: str, actor: AnyKey, session: Session, cache: KeyCacheDep) -> schemas.KeyRevoked:
    """Stop one of the org's keys from the next request on; a POST, so the row stays for the log."""
    for stopped in await keys.revoke_key(session, actor, fingerprint):
        cache.forget(fingerprint_=stopped)
    return schemas.KeyRevoked(fingerprint=fingerprint, revoked=True)
