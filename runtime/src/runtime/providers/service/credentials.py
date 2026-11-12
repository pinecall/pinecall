"""What the org and the box hold for each vendor: their credentials, sealed under the vault, opened to run a call."""

import json
import logging
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.exceptions import NotFound, ServiceUnavailable, ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.text import a_mapping
from runtime.platform import service as platform
from runtime.postgres import BoxSession
from runtime.providers.repository import BOX_CREDENTIALS, BoxCredentialRepository, ProviderKeyRepository
from runtime.providers.service import plugins, signatures
from runtime.providers.stage import Credentials

logger = logging.getLogger(__name__)

NOT_ONE_OF_THE_TWO = "a key, or the credentials object the vendor's plugin takes, and not both"

# What an org's credentials object may carry: the fields the vendor's constructors take, none of
# them an address, a file or a session. Where a vendor is reached is the operator's, in the
# providers row's tuning; a tenant's object that named one would aim the box's requests anywhere.
NOT_A_CREDENTIAL = frozenset({"url", "host", "endpoint", "session", "client", "transport", "connection", "model"})
NOT_A_CREDENTIAL_ENDS = ("_url", "_base", "_endpoint", "_host", "_file", "_path", "_session")
MOST_FIELDS = 8
LONGEST_VALUE = 1024


class NoKeyBrought(NotFound):
    """The org brought no key of its own for the vendor."""

    def __init__(self, whose: str, vendor: str) -> None:
        super().__init__(f"{whose} brought no key for {vendor}")


class NoBoxKey(NotFound):
    """The box holds no key for the vendor."""

    def __init__(self, vendor: str) -> None:
        super().__init__(f"this box holds no key for {vendor}")


# ── the org's own ──


async def own_credentials(session: AsyncSession, vault: Vault, org: str) -> dict[str, Credentials]:
    """The vendors' credentials the org brought, opened."""
    rows = await ProviderKeyRepository(session).list_of_org(org)
    return _open_rows(vault, [(row.vendor, row.ciphertext) for row in rows])


# Vendor names only, never a key or a prefix of one.
async def list_own_vendors(session: AsyncSession, org: str) -> list[str]:
    """The vendors the org brought its own credentials for, never the credentials."""
    return [row.vendor for row in await ProviderKeyRepository(session).list_of_org(org)]


async def put_own_credentials(
    session: AsyncSession, vault: Vault, org: str, vendor: str, credentials: Credentials
) -> None:
    """Keep the org's credentials for the vendor, replacing any it had."""
    await ProviderKeyRepository(session).put(org, vendor, _seal(vault, credentials))


async def take_key_back(session: AsyncSession, org: str, vendor: str, *, whose: str = "this org") -> None:
    """Forget the org's credentials for a vendor; its calls run on the box's from the next one."""
    named = plugins.parse_vendor(vendor)
    if not await ProviderKeyRepository(session).delete_of(org, named):
        raise NoKeyBrought(whose, named)


# ── the box's ──


async def box_credentials(session: AsyncSession, vault: Vault) -> dict[str, Credentials]:
    """The credentials the box holds for the vendors it offers, opened."""
    rows = await BoxCredentialRepository(session).list_sealed()
    return _open_rows(vault, [(row.name.removeprefix(BOX_CREDENTIALS), row.ciphertext or "") for row in rows])


# Offering a vendor is holding its key: the box's credentials, sealed, never read back. The box
# seals other accounts beside them (the one it buys numbers on), which are no vendor of a call:
# only what a plugin of this build runs is listed, so no account is named here to be left out.
async def list_box_vendors(session: AsyncSession, vault: Vault) -> list[str]:
    """The vendors of a call the box holds a key for, never the key."""
    return sorted(vendor for vendor in await box_credentials(session, vault) if plugins.is_installed(vendor))


# The session is the box's by its type. Until 2026-11 these two ran on whatever session the request
# had: an operator rotating the box's key with a key of their own was scoped to their org by
# row-level security, so only their org's copy followed and every other org's copy kept the old key.
async def put_box_credentials(session: BoxSession, vault: Vault, vendor: str, credentials: Credentials) -> None:
    """Keep the box's credentials for the vendor; an org's own copy of the key they replace takes them too."""
    copies = await _list_copies_of_the_boxs(session, vault, vendor)
    await platform.put_setting(session, _setting_of(vendor), None, ciphertext=_seal(vault, credentials))
    for org in copies:
        await put_own_credentials(session, vault, org, vendor, credentials)


async def drop_box_key(session: BoxSession, vault: Vault, vendor: str) -> None:
    """Stop offering the vendor on the box's key, an org's own copy of it with it; NotFound when it held none."""
    named = plugins.parse_vendor(vendor)
    for org in await _list_copies_of_the_boxs(session, vault, named):
        await ProviderKeyRepository(session).delete_of(org, named)
    if not await platform.delete_setting(session, _setting_of(named)):
        raise NoBoxKey(named)


# setup gives the org `default` each key it finds as its own too, so the operator's own agents may
# name a plugin's options, which run on an org's own key alone: a copy, which a rotated or dropped
# key of the box's must not leave behind on the old key.
async def _list_copies_of_the_boxs(session: BoxSession, vault: Vault, vendor: str) -> list[str]:
    held = (await box_credentials(session, vault)).get(vendor)
    if held is None:
        return []
    rows = await ProviderKeyRepository(session).list_of_vendor(vendor)
    return [row.org for row in rows if _open(vault, row.ciphertext) == held]


# ── what a body brings ──


def read_credentials(key: str | None, credentials: Mapping[str, Any] | None) -> Credentials:
    """One key, or the object the plugin takes; refused when neither or both."""
    if (key is None) == (credentials is None):
        raise ValidationError(NOT_ONE_OF_THE_TWO)
    if key is not None:
        if not key.strip():
            raise ValidationError(NOT_ONE_OF_THE_TWO)
        return key.strip()
    return credentials or {}


# Every field is one a constructor of the vendor takes, named for a secret and not for where it
# is sent, and a short scalar: nothing a plugin would open, dial or read a file by.
def check_credentials(vendor: str, credentials: Credentials) -> None:
    """Refuse a credentials object that names an address, a file, a session or a field untaken."""
    if not isinstance(credentials, Mapping):
        return
    if len(credentials) > MOST_FIELDS:
        raise ValidationError(f"{vendor} credentials carry {len(credentials)} fields: eight at most")
    taken = signatures.every_parameter_of(vendor)
    for name, value in credentials.items():
        lowered = name.lower()
        if lowered in NOT_A_CREDENTIAL or lowered.endswith(NOT_A_CREDENTIAL_ENDS):
            raise ValidationError(
                f"{vendor} credentials carry {name!r}: an address, a file or a session is the operator's "
                "to set in the providers row, not a credential"
            )
        if name not in taken:
            fields = ", ".join(sorted(taken)) or "nothing by name"
            raise ValidationError(f"{vendor} takes no credential named {name!r}; its plugin takes {fields}")
        if not isinstance(value, str | int | float | bool) or (
            isinstance(value, str) and (len(value) > LONGEST_VALUE or "://" in value)
        ):
            raise ValidationError(
                f"{vendor} credentials: {name!r} is a string, a number or a boolean of at most 1024 characters"
            )


# ── private ──


# A `credentials/<vendor>` row's value is empty: the secret is the ciphertext beside it.
def _no_value(_value: Mapping[str, Any]) -> None:
    return None


def _empty(_value: None) -> dict[str, Any]:
    return {}


def _setting_of(vendor: str) -> platform.Setting[None]:
    return platform.Setting(f"{BOX_CREDENTIALS}{vendor}", _no_value, _empty)


def _seal(vault: Vault, credentials: Credentials) -> str:
    plain: Any = credentials if isinstance(credentials, str) else dict(credentials)
    return vault.seal(json.dumps(plain))


# A token sealed under a key the list no longer holds reads as nothing, said in the log: one
# stale row must not stop every call of the org.
def _open_rows(vault: Vault, rows: list[tuple[str, str]]) -> dict[str, Credentials]:
    kept: dict[str, Credentials] = {}
    for vendor, ciphertext in rows:
        secret = _open(vault, ciphertext)
        if secret is None:
            logger.warning("the %s credentials are sealed under a key PINECALL_VAULT_KEY no longer lists", vendor)
            continue
        kept[vendor] = secret
    return kept


def _open(vault: Vault, ciphertext: str) -> Credentials | None:
    try:
        secret: object = json.loads(vault.open(ciphertext))
    except ServiceUnavailable:
        return None
    return secret if isinstance(secret, str) or a_mapping(secret) else None
