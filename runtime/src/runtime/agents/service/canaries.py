"""Canaries: one of a scope's versions on a share of an agent's calls, and which version each call runs."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents.models import AgentConfig
from runtime.agents.repository import AgentConfigRepository, CanaryRepository
from runtime.agents.service.versions import scope_to_write
from runtime.enums import Env
from runtime.exceptions import NotFound
from runtime.kit.text import sha256_of

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

    @property
    def version(self) -> int:
        """The version it puts on a share of the calls."""
        return self.canary.version

    @property
    def share(self) -> int:
        """How many calls in a hundred run that version."""
        return self.canary.share


@dataclass(frozen=True, slots=True)
class Shown:
    """What a canary's endpoints answer: the env, whose scope, and the canary it stands on, or none."""

    env: Env
    holder: str
    canary: StandingCanary | None


# sha256, not hash(): the same call lands in the same place in every process and every release.
def bucket_of(call: str) -> int:
    """The call's place among a hundred; a canary of share N takes the places under N."""
    return int(sha256_of(call)[:8], 16) % ALL_CALLS


# The rule was Python inside the repository until 2026-11, run over every version ever kept. The rows
# come nearest level first, each level newest first. A call whose bucket is under the share runs the
# canary's version, every other the newest but that one; a `version` named is the holder's own,
# whatever canary stands.
def pick(
    rows: Sequence[AgentConfig], standing: Mapping[str, Canary], *, holder: str, bucket: int | None, version: int | None
) -> list[AgentConfig]:
    """The row of each level a call is built from, nearest first."""
    chosen: dict[str, AgentConfig] = {}
    for row in rows:
        if row.holder in chosen:
            continue
        if version is not None and row.holder == holder:
            if row.version == version:
                chosen[row.holder] = row
            continue
        canary = standing.get(row.holder)
        if canary is None:
            chosen[row.holder] = row
            continue
        in_its_share = bucket is not None and bucket < canary.share
        if (row.version == canary.version) == in_its_share:
            chosen[row.holder] = row
    return [chosen[level] for level in sorted(chosen, reverse=True)]


async def standing_per_level(session: AsyncSession, scope: Scope, agent: str) -> dict[str, Canary]:
    """The canary each level of the scope stands on now (the holder's, the org's); a cleared one is none."""
    rows = await CanaryRepository(session).standing_per_level(scope, agent)
    return {level: Canary(row.version, row.share or 0) for level, row in rows.items() if row.version is not None}


async def find_standing(session: AsyncSession, scope: Scope, agent: str) -> StandingCanary | None:
    """The scope's own canary for the agent, or None when none stands or it was cleared."""
    row = await CanaryRepository(session).find_standing(scope, agent)
    if row is None or row.version is None or row.share is None:
        return None
    return StandingCanary(row.holder, Canary(row.version, row.share), row.author, row.note, row.set_at)


# A key holding no agent writes the org's own scope: no call resolves in its holder's.
async def show_canary(session: AsyncSession, scope: Scope, agent: str, *, team: bool) -> Shown:
    """The version the key's scope, or the team's, runs on a share of the agent's calls, or none."""
    target = scope_to_write(scope, team=team)
    return Shown(scope.env, target.holder, await find_standing(session, target, agent))


# The pipeline's alone, as the vendors are: a canary decides what a share of the calls runs.
async def set_canary(
    session: AsyncSession, scope: Scope, agent: str, canary: Canary, *, author: str, note: str | None, team: bool
) -> Shown:
    """One of the scope's versions on a share of the agent's calls; the rest run the others."""
    target = scope_to_write(scope, team=team)
    row = await AgentConfigRepository(session).find_at(target, agent, canary.version)
    if row is None or row.holder != target.holder:
        raise NoSuchVersion(canary.version, agent)
    await CanaryRepository(session).add_row(
        target, agent, version=canary.version, share=canary.share, author=author, note=note
    )
    return await show_canary(session, scope, agent, team=team)


# Cleared, every call runs the scope's newest version again, the canary's included.
async def clear_canary(session: AsyncSession, scope: Scope, agent: str, *, author: str, team: bool) -> Shown:
    """The scope's canary cleared: one version for every call."""
    target = scope_to_write(scope, team=team)
    if await find_standing(session, target, agent) is not None:
        await CanaryRepository(session).add_row(target, agent, version=None, share=None, author=author, note=None)
    return await show_canary(session, scope, agent, team=team)


async def is_canary_run(session: AsyncSession, scope: Scope, agent: str, version: int | None, at: datetime) -> bool:
    """Whether a call that opened then on this version was one of a canary's share."""
    if version is None:
        return False
    rows = await CanaryRepository(session).standing_per_level(scope, agent, at=at)
    return any(row.version == version and row.share for row in rows.values())
