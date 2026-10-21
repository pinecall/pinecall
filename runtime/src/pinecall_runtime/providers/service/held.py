"""What the org and the box hold for each vendor: their credentials, sealed under the vault, opened to run a call."""

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.exceptions import ServiceUnavailable, ValidationError
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.text import a_mapping
from pinecall_runtime.providers.repository import BoxCredentialRepository, ProviderKeyRepository, vendor_of
from pinecall_runtime.providers.schemas import ProviderKeyRequest
from pinecall_runtime.providers.service.plugins import Credentials

logger = logging.getLogger(__name__)


async def own_credentials(session: AsyncSession, vault: Vault, org: str) -> dict[str, Credentials]:
    """The vendors' credentials the org brought, opened."""
    rows = await ProviderKeyRepository(session).of_org(org)
    return _opened_rows(vault, [(row.vendor, row.ciphertext) for row in rows])


async def own_vendors(session: AsyncSession, org: str) -> list[str]:
    """The vendors the org brought its own credentials for, never the credentials."""
    return [row.vendor for row in await ProviderKeyRepository(session).of_org(org)]


async def put_own_credentials(
    session: AsyncSession, vault: Vault, org: str, vendor: str, credentials: Credentials
) -> None:
    """Keep the org's credentials for the vendor, replacing any it had."""
    await ProviderKeyRepository(session).put(org, vendor, _sealed(vault, credentials))


async def drop_own_credentials(session: AsyncSession, org: str, vendor: str) -> bool:
    """Forget the org's credentials for the vendor; whether it had any."""
    return await ProviderKeyRepository(session).drop(org, vendor)


async def box_credentials(session: AsyncSession, vault: Vault) -> dict[str, Credentials]:
    """The credentials the box holds for the vendors it offers, opened."""
    rows = await BoxCredentialRepository(session).all_vendors()
    return _opened_rows(vault, [(vendor_of(row), row.ciphertext or "") for row in rows])


async def put_box_credentials(session: AsyncSession, vault: Vault, vendor: str, credentials: Credentials) -> None:
    """Keep the box's credentials for the vendor; an org's own copy of the key they replace takes them too."""
    copies = await _copies_of_the_boxs(session, vault, vendor)
    await BoxCredentialRepository(session).put(vendor, _sealed(vault, credentials))
    for org in copies:
        await put_own_credentials(session, vault, org, vendor, credentials)


async def drop_box_credentials(session: AsyncSession, vault: Vault, vendor: str) -> bool:
    """Stop offering the vendor on the box's key, an org's own copy of it with it; whether the box held one."""
    for org in await _copies_of_the_boxs(session, vault, vendor):
        await drop_own_credentials(session, org, vendor)
    return await BoxCredentialRepository(session).drop(vendor)


# setup gives the org `default` each key it finds as its own too, so the operator's own agents may
# name a plugin's options, which run on an org's own key alone: a copy, which a rotated or dropped
# key of the box's must not leave behind on the old key.
async def _copies_of_the_boxs(session: AsyncSession, vault: Vault, vendor: str) -> list[str]:
    held = (await box_credentials(session, vault)).get(vendor)
    if held is None:
        return []
    rows = await ProviderKeyRepository(session).of_vendor(vendor)
    return [row.org for row in rows if _opened(vault, row.ciphertext) == held]


def credentials_from(body: ProviderKeyRequest) -> Credentials:
    """One key, or the object the plugin takes, out of the body; refused when neither or both."""
    if (body.key is None) == (body.credentials is None):
        raise ValidationError("a key, or the credentials object the vendor's plugin takes, and not both")
    if body.key is not None:
        if not body.key.strip():
            raise ValidationError("a key, or the credentials object the vendor's plugin takes, and not both")
        return body.key.strip()
    return body.credentials or {}


def _sealed(vault: Vault, credentials: Credentials) -> str:
    plain: Any = credentials if isinstance(credentials, str) else dict(credentials)
    return vault.seal(json.dumps(plain))


# A token sealed under a key the list no longer holds reads as nothing, said in the log: one
# stale row must not stop every call of the org.
def _opened_rows(vault: Vault, rows: list[tuple[str, str]]) -> dict[str, Credentials]:
    kept: dict[str, Credentials] = {}
    for vendor, ciphertext in rows:
        secret = _opened(vault, ciphertext)
        if secret is None:
            logger.warning("the %s credentials are sealed under a key PINECALL_VAULT_KEY no longer lists", vendor)
            continue
        kept[vendor] = secret
    return kept


def _opened(vault: Vault, ciphertext: str) -> Credentials | None:
    try:
        secret: object = json.loads(vault.open(ciphertext))
    except ServiceUnavailable:
        return None
    return secret if isinstance(secret, str) or a_mapping(secret) else None
