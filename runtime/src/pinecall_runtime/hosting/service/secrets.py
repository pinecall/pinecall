"""An org's secrets in an env: the values its hosted apps are started with, kept sealed."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound, ServiceUnavailable, ValidationError
from pinecall_runtime.hosting.models import OrgSecret
from pinecall_runtime.hosting.repository import SecretRepository
from pinecall_runtime.kit.crypto import Vault

# An environment variable's name, as a shell takes it.
A_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
# What the box sets itself on every process it starts.
RESERVED = "PINECALL_"
LONGEST_VALUE = 16 * 1024

NOT_A_NAME = "{name!r} is not a secret's name: capitals, digits and underscores, like CRM_TOKEN"
IS_THE_BOXS = "{name} is the box's to set: a name starting with PINECALL_ is never an org's secret"
TOO_LONG = "a secret is {limit} KB at most"
NOT_SET = "the org has no secret called {name} in {env}"


@dataclass(frozen=True, slots=True)
class Secret:
    """One secret written: the env it is for, its name and its value."""

    env: Env
    name: str
    value: str

    def __post_init__(self) -> None:
        if not A_NAME.match(self.name):
            raise ValidationError(NOT_A_NAME.format(name=self.name))
        if self.name.startswith(RESERVED):
            raise ValidationError(IS_THE_BOXS.format(name=self.name))
        if len(self.value.encode()) > LONGEST_VALUE:
            raise ValidationError(TOO_LONG.format(limit=LONGEST_VALUE >> 10))


async def put_secret(session: AsyncSession, vault: Vault, org: str, secret: Secret, *, by: str) -> None:
    """Keep the org's secret, sealed, replacing the value it had."""
    await SecretRepository(session).put(org, secret.env, secret.name, sealed=vault.seal(secret.value), set_by=by)


async def list_secrets(session: AsyncSession, org: str, env: Env) -> Sequence[OrgSecret]:
    """The org's secrets in the env, by name: who set each and when; the values stay sealed."""
    return await SecretRepository(session).of_env(org, env)


# A value no listed vault key opens is left out: the process starts without it and says so itself.
async def environment_of(session: AsyncSession, vault: Vault, org: str, env: Env) -> dict[str, str]:
    """The org's secrets in the env, opened, by name: what a hosted app is started with."""
    opened: dict[str, str] = {}
    for row in await SecretRepository(session).of_env(org, env):
        try:
            opened[row.name] = vault.open(row.sealed)
        except ServiceUnavailable:
            continue
    return opened


async def delete_secret(session: AsyncSession, org: str, env: Env, name: str) -> None:
    """Forget one of the org's secrets; NotFound for a name nobody set."""
    if not await SecretRepository(session).drop(org, env, name):
        raise NotFound(NOT_SET.format(name=name, env=env.value))
