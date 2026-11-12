"""An org's secrets in an env: listed by name, kept sealed, forgotten; never a value answered."""

from fastapi import APIRouter

from runtime.actor import Actor
from runtime.handles import TheSignal, TheVault
from runtime.hosting import schemas
from runtime.hosting.service import apps, secrets
from runtime.live.auth import AppKey
from runtime.postgres import Session

router = APIRouter()

# A secret set or forgotten is said as a change of the org's apps: whoever holds them reads its secrets again.


@router.get("/v1/secrets")
async def list_secrets(actor: AppKey, session: Session) -> schemas.SecretList:
    """The org's secrets in this env, by name; never a value."""
    return await _list(session, actor)


@router.put("/v1/secrets/{name}")
async def put_secret(
    name: str, body: schemas.PutSecretRequest, actor: AppKey, vault: TheVault, signal: TheSignal, session: Session
) -> schemas.SecretList:
    """Keep one secret, sealed, replacing the value it had; the org's list after it."""
    secret = secrets.Secret(env=actor.env, name=name, value=body.value)
    await secrets.put_secret(session, vault, actor.org, secret, by=apps.name_asker(actor))
    apps.tell_changed(session, signal, apps.App(actor.org, actor.env, name))
    return await _list(session, actor)


@router.delete("/v1/secrets/{name}")
async def delete_secret(name: str, actor: AppKey, signal: TheSignal, session: Session) -> schemas.SecretList:
    """Forget one secret; the org's list after it, 404 for a name nobody set."""
    await secrets.delete_secret(session, actor.org, actor.env, name)
    apps.tell_changed(session, signal, apps.App(actor.org, actor.env, name))
    return await _list(session, actor)


async def _list(session: Session, actor: Actor) -> schemas.SecretList:
    listed = await secrets.list_secrets(session, actor.org, actor.env)
    return schemas.SecretList(secrets=[schemas.SecretRow.of(secret) for secret in listed])
