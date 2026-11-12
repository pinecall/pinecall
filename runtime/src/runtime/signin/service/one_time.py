"""Secrets spent once, kept in Postgres sealed, so one minted on any gateway is spent on any other."""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.kit.crypto import Vault, random_token
from runtime.kit.time import epoch
from runtime.signin.models import OneTimeSecret
from runtime.signin.repository import OneTimeSecretRepository

SECRET_BYTES = 24


@dataclass(frozen=True, slots=True)
class Kind:
    """One kind of one-time secret: what its secrets start with, and how long one lives."""

    prefix: str
    ttl_s: float


@dataclass(frozen=True, slots=True)
class Kept[T]:
    """A value kept under a one-time secret, until when, and how many guesses at it were counted."""

    value: T
    expires_at: float
    attempts: int = 0


@dataclass(frozen=True, slots=True)
class Minted:
    """A secret just minted, handed over this once, and when it dies in epoch seconds."""

    code: str
    expires_at: float


# A value is kept as JSON, sealed: its owner gives the two plain functions that read and write it,
# so the store knows no shape. The field names are the ones the previous runtime wrote, so a secret
# minted by a gateway of either is spent by a gateway of the other while both run.
#
# Each verb has two reaches. On its own it runs in a transaction of its own, committed whatever the
# request does next: a secret spent stays spent, a guess counted stays counted. The `_on` verbs write
# in the caller's transaction, for what follows a request's own work: the secret exists only if that
# work is committed, and the request holds one connection and never waits for a second.
class OneTimeSecrets[T]:
    """Secrets of one kind, each dying on its own, their values sealed under the vault."""

    def __init__(
        self,
        kind: Kind,
        sessions: async_sessionmaker[AsyncSession],
        vault: Vault,
        *,
        load: Callable[[Mapping[str, Any]], T],
        dump: Callable[[T], dict[str, Any]],
        clock: Callable[[], float] = epoch,
    ) -> None:
        self.kind = kind
        self.sessions = sessions
        self.vault = vault
        self.clock = clock
        self._load = load
        self._dump = dump

    def new_secret(self) -> str:
        """A fresh secret, not yet holding anything."""
        return f"{self.kind.prefix}{random_token(SECRET_BYTES)}"

    async def keep(self, secret: str, value: T) -> float:
        """Hold the value under the secret until it dies, and say when."""
        async with self.sessions.begin() as session:
            return await self.keep_on(session, secret, value)

    async def keep_on(self, session: AsyncSession, secret: str, value: T) -> float:
        """Hold the value under the secret in the caller's transaction, and say when it dies."""
        moment = self.clock()
        expires_at = moment + self.kind.ttl_s
        secrets = OneTimeSecretRepository(session)
        await secrets.sweep(moment)
        await secrets.put(_hash(secret), self.kind.prefix, self._seal(value), expires_at)
        return expires_at

    async def mint(self, value: T) -> Minted:
        """A new secret holding the value, and when it dies."""
        secret = self.new_secret()
        return Minted(secret, await self.keep(secret, value))

    async def mint_on(self, session: AsyncSession, value: T) -> Minted:
        """A new secret holding the value, kept in the caller's transaction, and when it dies."""
        secret = self.new_secret()
        return Minted(secret, await self.keep_on(session, secret, value))

    async def read(self, secret: str) -> Kept[T] | None:
        """What the secret holds, dead or not, without spending it."""
        async with self.sessions() as session:
            row = await OneTimeSecretRepository(session).find(_hash(secret))
        return None if row is None else self._read_row(row)

    async def read_alive(self, secret: str) -> Kept[T] | None:
        """What the secret holds while it lives, without spending it."""
        kept = await self.read(secret)
        return None if kept is None or kept.expires_at <= self.clock() else kept

    async def spend(self, secret: str) -> T | None:
        """What the secret holds, spent: it opens nothing after."""
        async with self.sessions.begin() as session:
            return await self.spend_on(session, secret)

    async def spend_on(self, session: AsyncSession, secret: str) -> T | None:
        """What the secret holds, spent in the caller's transaction: a rollback leaves it to be spent again."""
        row = await OneTimeSecretRepository(session).spend(_hash(secret), self.clock())
        return None if row is None else self._open(row.sealed)

    async def fill_on(self, session: AsyncSession, secret: str, value: T) -> bool:
        """Change what a living secret holds, its end kept, in the caller's transaction; False for a dead one."""
        return await OneTimeSecretRepository(session).fill(_hash(secret), self._seal(value), self.clock())

    async def take_attempt(self, secret: str, most: int) -> Kept[T] | None:
        """Count one guess at a living secret that has any of its `most` left; None when it has none."""
        async with self.sessions.begin() as session:
            row = await OneTimeSecretRepository(session).take_attempt(_hash(secret), self.clock(), most)
            return None if row is None else self._read_row(row)

    async def forget(self, secret: str) -> None:
        """The secret opens nothing from now on."""
        async with self.sessions.begin() as session:
            await OneTimeSecretRepository(session).forget(_hash(secret))

    def _read_row(self, row: OneTimeSecret) -> Kept[T]:
        return Kept(self._open(row.sealed), row.expires_at, row.attempts)

    def _seal(self, value: T) -> str:
        return self.vault.seal(json.dumps(self._dump(value)))

    def _open(self, sealed: str) -> T:
        return self._load(json.loads(self.vault.open(sealed)))


def _hash(secret: str) -> bytes:
    return hashlib.sha256(secret.encode()).digest()
