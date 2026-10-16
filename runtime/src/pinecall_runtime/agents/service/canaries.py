"""Canaries: one of a scope's versions on a share of an agent's calls, and which calls fall in it."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.repository import AgentConfigRepository, CanaryRepository
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit.auth import Scope

# A share is a whole percent of the scope's calls.
ALL_CALLS = 100


class NoSuchVersion(NotFound):
    """No version by that number in the scope."""

    def __init__(self, version: int, slug: str) -> None:
        super().__init__(f"no version {version} in this scope of {slug}")


@dataclass(frozen=True, slots=True)
class Canary:
    """Which version takes a share of the calls, and how many in a hundred."""

    version: int
    share: int


@dataclass(frozen=True, slots=True)
class StandingCanary:
    """The canary a scope stands on now: whose, which, who set it, why and when."""

    holder: str
    canary: Canary
    author: str
    note: str | None
    set_at: datetime


# sha256, not hash(): the same call lands in the same place in every process and every release.
def bucket_of(call: str) -> int:
    """The call's place among a hundred; a canary of share N takes the places under N."""
    return int(sha256(call.encode()).hexdigest()[:8], 16) % ALL_CALLS


async def standing_canary(session: AsyncSession, scope: Scope, agent: str) -> StandingCanary | None:
    """The scope's own canary for the agent, or None when none stands or it was cleared."""
    row = await CanaryRepository(session).standing(scope, agent)
    if row is None or row.version is None or row.share is None:
        return None
    return StandingCanary(row.holder, Canary(row.version, row.share), row.author, row.note, row.set_at)


async def set_canary(
    session: AsyncSession, scope: Scope, agent: str, canary: Canary, *, author: str, note: str | None, at: datetime
) -> None:
    """One of the scope's versions on a share of the agent's calls."""
    row = await AgentConfigRepository(session).at(scope, agent, canary.version)
    if row is None or row.holder != scope.holder:
        raise NoSuchVersion(canary.version, agent)
    await CanaryRepository(session).put(
        scope, agent, version=canary.version, share=canary.share, author=author, note=note, at=at
    )


async def clear_canary(session: AsyncSession, scope: Scope, agent: str, *, author: str, at: datetime) -> None:
    """Every call runs the scope's newest version again."""
    if await standing_canary(session, scope, agent) is not None:
        await CanaryRepository(session).put(scope, agent, version=None, share=None, author=author, note=None, at=at)


async def ran_the_canary(session: AsyncSession, scope: Scope, agent: str, version: int | None, at: datetime) -> bool:
    """Whether a call that opened then on this version was one of a canary's share."""
    if version is None:
        return False
    rows = await CanaryRepository(session).standing_per_level(scope, agent, at=at)
    return any(row.version == version and row.share for row in rows.values())
