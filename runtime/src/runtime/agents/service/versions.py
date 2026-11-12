"""What an org sets on an agent, kept in versions per scope: read by level, written under a lock, never changed."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import THE_ORGS_OWN, Scope
from runtime.agents.models import AgentConfig
from runtime.agents.models import Lexicon as LexiconRow
from runtime.agents.repository import AgentConfigRepository, LexiconRepository, VersionedRepository
from runtime.agents.settings import AgentSettings, Lexicon, dump_settings, read_settings
from runtime.enums import Env
from runtime.exceptions import Conflict

HISTORY_LIMIT = 20


class VersionMoved(Conflict):
    """The scope was written since the writer read it."""

    def __init__(self, newest: int) -> None:
        super().__init__(f"this scope is at v{newest} now, not the version you read: read it again, then set again")


@dataclass(frozen=True, slots=True)
class Version[T]:
    """A stored version of a value, with its holder, number, author and timestamp."""

    holder: str
    version: int
    author: str
    note: str | None
    set_at: datetime
    value: T


@dataclass(frozen=True, slots=True)
class Written:
    """Who writes a version, why, and the version they read when they want no other."""

    author: str
    note: str | None = None
    if_version: int | None = None


@dataclass(frozen=True, slots=True)
class SideBySide[T]:
    """What a settings screen shows side by side: yours, the team's and production's newest."""

    yours: Version[T] | None
    team: Version[T] | None
    production: Version[T] | None

    def own_of(self, scope: Scope) -> Version[T] | None:
        """The newest of the scope's own level: the team's for the org's own scope, else yours."""
        return self.team if scope.holder == THE_ORGS_OWN else self.yours


# Settings and the lexicon are two of these; a third thing kept in versions is one more line below.
@dataclass(frozen=True, slots=True)
class Versioned[M: (AgentConfig, LexiconRow), T]:
    """One thing kept in versions: its table's repository, and its value read off a row and written onto one."""

    repository: type[VersionedRepository[M]]
    read: Callable[[M], T]
    columns: Callable[[T], dict[str, Any]]

    def version_of(self, row: M) -> Version[T]:
        """A row as the version it is."""
        return Version(row.holder, row.version, row.author, row.note, row.set_at, self.read(row))


def scope_to_write(scope: Scope, *, team: bool) -> Scope:
    """The scope a write lands in: the key's own, or the team's."""
    return replace(scope, holder=THE_ORGS_OWN) if team else scope


# A row is given its shape and nothing more: a rule made stricter since it was written is asked of the
# next write, never of a row already kept (`settings.check_settings`).
def _settings_of(row: AgentConfig) -> AgentSettings:
    return read_settings(row.config)


def _settings_columns(settings: AgentSettings) -> dict[str, Any]:
    return {"config": dump_settings(settings)}


def _lexicon_of(row: LexiconRow) -> Lexicon:
    said = {str(word): str(spoken) for word, spoken in row.said.items()}
    return Lexicon(said=said, heard=tuple(str(word) for word in row.heard))


def _lexicon_columns(lexicon: Lexicon) -> dict[str, Any]:
    return {"said": dict(lexicon.said), "heard": list(lexicon.heard)}


SETTINGS: Versioned[AgentConfig, AgentSettings] = Versioned(AgentConfigRepository, _settings_of, _settings_columns)
LEXICON: Versioned[LexiconRow, Lexicon] = Versioned(LexiconRepository, _lexicon_of, _lexicon_columns)


async def find_newest[M: (AgentConfig, LexiconRow), T](
    session: AsyncSession, kind: Versioned[M, T], scope: Scope, agent: str
) -> Version[T] | None:
    """The scope's own newest version, none falling through; None when it never set any."""
    row = await kind.repository(session).find_newest(scope, agent)
    return None if row is None else kind.version_of(row)


async def find_version[M: (AgentConfig, LexiconRow), T](
    session: AsyncSession, kind: Versioned[M, T], scope: Scope, agent: str, version: int
) -> Version[T] | None:
    """One version, the scope's own or the org's it fell through to."""
    row = await kind.repository(session).find_at(scope, agent, version)
    return None if row is None else kind.version_of(row)


async def list_history[M: (AgentConfig, LexiconRow), T](
    session: AsyncSession, kind: Versioned[M, T], scope: Scope, agent: str, *, limit: int = HISTORY_LIMIT
) -> list[Version[T]]:
    """The scope's own versions, newest first."""
    return [kind.version_of(row) for row in await kind.repository(session).list_history(scope, agent, limit=limit)]


async def side_by_side[M: (AgentConfig, LexiconRow), T](
    session: AsyncSession, kind: Versioned[M, T], scope: Scope, agent: str
) -> SideBySide[T]:
    """Yours, the team's and production's newest, none falling through."""
    return SideBySide(
        yours=await find_newest(session, kind, scope, agent) if scope.holder else None,
        team=await find_newest(session, kind, replace(scope, holder=THE_ORGS_OWN), agent),
        production=await find_newest(session, kind, Scope(scope.org, Env.production), agent),
    )


# The lock is taken before the newest version is read, and held to the commit: two writers of one scope
# go one after the other, the second reads what the first wrote, and `if_version` refuses it by sentence.
async def add_version[M: (AgentConfig, LexiconRow), T](
    session: AsyncSession, kind: Versioned[M, T], scope: Scope, agent: str, value: T, written: Written
) -> int:
    """Write the scope's next version; a scope moved since it was read refuses."""
    repository = kind.repository(session)
    await repository.lock(scope, agent)
    newest = await repository.newest_version(scope, agent)
    if written.if_version is not None and newest != written.if_version:
        raise VersionMoved(newest)
    row = await repository.add_version(
        scope, agent, newest + 1, author=written.author, note=written.note, **kind.columns(value)
    )
    return row.version
