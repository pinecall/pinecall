"""Secrets spent once, kept in Postgres sealed, so one minted on any gateway is spent on any other."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.repository import OneUseWordRepository
from pinecall_runtime.kit.crypto import Vault, random_token
from pinecall_runtime.kit.time import epoch

SECRET_BYTES = 24


@dataclass(frozen=True, slots=True)
class Kept[T]:
    """A value kept under a one-time secret, until when, and how often a guess at it failed."""

    value: T
    expires_at: float
    attempts: int = 0


class OneTimeSecrets[T]:
    """Secrets of one kind, each dying on its own, their values sealed under the vault."""

    def __init__(
        self,
        prefix: str,
        ttl_s: float,
        adapter: TypeAdapter[T],
        sessions: async_sessionmaker[AsyncSession],
        vault: Vault,
        clock: Callable[[], float] = epoch,
    ) -> None:
        self.prefix = prefix
        self.ttl_s = ttl_s
        self.adapter = adapter
        self.sessions = sessions
        self.vault = vault
        self.clock = clock

    def new_secret(self) -> str:
        """A fresh secret, not yet holding anything."""
        return f"{self.prefix}{random_token(SECRET_BYTES)}"

    async def keep(self, secret: str, value: T) -> float:
        """Hold the value under the secret until it dies, and say when."""
        moment = self.clock()
        expires_at = moment + self.ttl_s
        async with self.sessions() as session:
            words = OneUseWordRepository(session)
            await words.sweep(moment)
            await words.put(_hashed(secret), self.prefix, self._seal(value), expires_at)
            await session.commit()
        return expires_at

    async def mint(self, value: T) -> tuple[str, float]:
        """A new secret holding the value, and when it dies."""
        secret = self.new_secret()
        return secret, await self.keep(secret, value)

    async def read(self, secret: str) -> Kept[T] | None:
        """What the secret holds, dead or not, without spending it."""
        async with self.sessions() as session:
            row = await OneUseWordRepository(session).get(_hashed(secret))
        if row is None:
            return None
        return Kept(self._open(row.sealed), row.expires_at, row.attempts)

    async def read_alive(self, secret: str) -> Kept[T] | None:
        """What the secret holds while it lives, without spending it."""
        kept = await self.read(secret)
        return None if kept is None or kept.expires_at <= self.clock() else kept

    async def spend(self, secret: str) -> T | None:
        """What the secret holds, spent: it opens nothing after."""
        async with self.sessions() as session:
            row = await OneUseWordRepository(session).spend(_hashed(secret), self.clock())
            await session.commit()
        return None if row is None else self._open(row.sealed)

    async def fill(self, secret: str, value: T) -> bool:
        """Change what a living secret holds, its end kept; False for a dead one."""
        async with self.sessions() as session:
            filled = await OneUseWordRepository(session).fill(_hashed(secret), self._seal(value), self.clock())
            await session.commit()
        return filled

    async def count_attempt(self, secret: str) -> int:
        """One more wrong guess; how many there were."""
        async with self.sessions() as session:
            attempts = await OneUseWordRepository(session).count_attempt(_hashed(secret))
            await session.commit()
        return attempts

    async def forget(self, secret: str) -> None:
        """The secret opens nothing from now on."""
        async with self.sessions() as session:
            await OneUseWordRepository(session).forget(_hashed(secret))
            await session.commit()

    def _seal(self, value: T) -> str:
        return self.vault.seal(self.adapter.dump_json(value).decode())

    def _open(self, sealed: str) -> T:
        return self.adapter.validate_json(self.vault.open(sealed))


def _hashed(secret: str) -> bytes:
    return hashlib.sha256(secret.encode()).digest()
