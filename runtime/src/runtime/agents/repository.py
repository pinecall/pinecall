"""Every statement on the agents tables: versions of settings and lexicon, canaries, declarations, widgets, melodies."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, literal, or_, select
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.orm import aliased

from runtime.actor import THE_ORGS_OWN, Scope
from runtime.agents.models import (
    AgentCanary,
    AgentConfig,
    AgentDeclaration,
    AgentDocument,
    AgentLine,
    AgentWidget,
    HoldAudio,
    Lexicon,
)
from runtime.enums import Env, HoldPlayed
from runtime.kit.repository import Repository
from runtime.kit.time import now

type Levelled = type[AgentConfig] | type[Lexicon] | type[AgentDeclaration] | type[AgentCanary]

# What a call is built from, per level: the newest row and the one before it (the newest that is not a
# canary's), beside the versions named.
NEWEST_READ = 2


# Settings and the lexicon are kept the same way: a row per version, per scope, never changed. Until
# 2026-11 each had this class written out, and neither took a lock: two writers of one scope both read
# the newest version, both inserted the next, and the second met the primary key as a 500.
class VersionedRepository[M: (AgentConfig, Lexicon)](Repository[M]):
    """The versions of something an org sets on an agent, per scope: only ever added."""

    async def lock(self, scope: Scope, agent: str) -> None:
        """Hold the scope's versions of the agent for this transaction: the next writer waits, then reads."""
        named = f"versions {self.model.__tablename__} {scope.org}|{scope.env}|{scope.holder}|{agent}"
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext(literal(named)))))

    async def newest_version(self, scope: Scope, agent: str) -> int:
        """The newest version number in the scope; 0 when none."""
        statement = select(func.coalesce(func.max(self.model.version), 0)).where(*_in_scope(self.model, scope, agent))
        return int((await self.session.execute(statement)).scalar_one())

    async def find_newest(self, scope: Scope, agent: str) -> M | None:
        """The scope's own newest version, none falling through."""
        statement = self.statement().where(*_in_scope(self.model, scope, agent))
        return await self.one_or_none(statement.order_by(self.model.version.desc()).limit(1))

    async def find_at(self, scope: Scope, agent: str, version: int) -> M | None:
        """One version: the holder's, or the org's it fell through to."""
        statement = self.statement().where(*_in_scope_or_orgs(self.model, scope, agent), self.model.version == version)
        return await self.one_or_none(statement.order_by(self.model.holder.desc()).limit(1))

    async def list_history(self, scope: Scope, agent: str, *, limit: int) -> Sequence[M]:
        """The scope's own versions, newest first."""
        statement = self.statement().where(*_in_scope(self.model, scope, agent))
        return await self.all(statement.order_by(self.model.version.desc()).limit(limit))

    async def add_version(self, scope: Scope, agent: str, version: int, **columns: Any) -> M:
        """The version, added to the scope; the caller holds the lock and read the newest under it."""
        return await self.add(
            self.model(org=scope.org, env=scope.env, holder=scope.holder, agent=agent, version=version, **columns)
        )


class AgentConfigRepository(VersionedRepository[AgentConfig]):
    """The versions of an agent's settings in a scope."""

    model = AgentConfig

    # Until 2026-11 every version ever kept, of both levels, was read to build each call.
    async def list_candidates(self, scope: Scope, agent: str, versions: Sequence[int]) -> Sequence[AgentConfig]:
        """Each level's newest rows and the versions named: the holder's level first, each newest first."""
        place = func.row_number().over(partition_by=AgentConfig.holder, order_by=AgentConfig.version.desc())
        ranked = (
            select(AgentConfig, place.label("place")).where(*_in_scope_or_orgs(AgentConfig, scope, agent)).subquery()
        )
        row = aliased(AgentConfig, ranked)
        statement = select(row).where(or_(ranked.c.place <= NEWEST_READ, row.version.in_(versions)))
        return await self.all(statement.order_by(row.holder.desc(), row.version.desc()))

    async def list_newest_per_agent(self, scope: Scope) -> Sequence[AgentConfig]:
        """Every agent's newest row at each level of the scope: an agent's holder's level before its org's."""
        statement = (
            self.statement()
            .where(
                AgentConfig.org == scope.org,
                AgentConfig.env == scope.env,
                AgentConfig.holder.in_((scope.holder, THE_ORGS_OWN)),
            )
            .ext(distinct_on(AgentConfig.agent, AgentConfig.holder))
            .order_by(AgentConfig.agent, AgentConfig.holder.desc(), AgentConfig.version.desc())
        )
        return await self.all(statement)

    async def list_noted(
        self, scope: Scope, agent: str, versions: Sequence[int], since: datetime, until: datetime
    ) -> Sequence[AgentConfig]:
        """The versions named, and those set in [since, until), oldest first."""
        return await self.all(
            self.statement()
            .where(
                *_in_scope_or_orgs(AgentConfig, scope, agent),
                or_(AgentConfig.version.in_(versions), (AgentConfig.set_at >= since) & (AgentConfig.set_at < until)),
            )
            .order_by(AgentConfig.version, AgentConfig.holder.desc())
        )


class LexiconRepository(VersionedRepository[Lexicon]):
    """The versions of an agent's lexicon in a scope."""

    model = Lexicon

    async def find_nearest(self, scope: Scope, agent: str) -> Lexicon | None:
        """The newest row of the holder's level, else the org's."""
        statement = self.statement().where(*_in_scope_or_orgs(Lexicon, scope, agent))
        return await self.one_or_none(statement.order_by(Lexicon.holder.desc(), Lexicon.version.desc()).limit(1))


class CanaryRepository(Repository[AgentCanary]):
    """A version of an agent's settings on a share of its calls; rows are only ever added."""

    model = AgentCanary

    async def find_standing(self, scope: Scope, agent: str) -> AgentCanary | None:
        """The scope's own newest row, cleared or not."""
        statement = self.statement().where(*_in_scope(AgentCanary, scope, agent))
        return await self.one_or_none(statement.order_by(AgentCanary.set_at.desc(), AgentCanary.id.desc()).limit(1))

    async def standing_per_level(
        self, scope: Scope, agent: str, *, at: datetime | None = None
    ) -> dict[str, AgentCanary]:
        """Each level's newest row (the holder's and the org's), at a moment or now."""
        statement = self.statement().where(*_in_scope_or_orgs(AgentCanary, scope, agent))
        if at is not None:
            statement = statement.where(AgentCanary.set_at <= at)
        newest = statement.ext(distinct_on(AgentCanary.holder)).order_by(
            AgentCanary.holder, AgentCanary.set_at.desc(), AgentCanary.id.desc()
        )
        return {row.holder: row for row in await self.all(newest)}

    async def add_row(
        self, scope: Scope, agent: str, *, version: int | None, share: int | None, author: str, note: str | None
    ) -> AgentCanary:
        """Set the canary, or clear it with a row that names no version."""
        return await self.add(
            AgentCanary(
                org=scope.org,
                env=scope.env,
                holder=scope.holder,
                agent=agent,
                version=version,
                share=share,
                author=author,
                note=note,
                set_at=now(),
            )
        )


class DeclarationRepository(Repository[AgentDeclaration]):
    """The last declaration each scope's app made of an agent."""

    model = AgentDeclaration

    async def find(self, scope: Scope, agent: str) -> AgentDeclaration | None:
        """The scope's own declaration, else the org's own in the env; None when neither declared the agent."""
        statement = self.statement().where(*_in_scope_or_orgs(AgentDeclaration, scope, agent))
        return await self.one_or_none(statement.order_by(AgentDeclaration.holder.desc()).limit(1))

    async def find_own(self, scope: Scope, agent: str) -> AgentDeclaration | None:
        """The scope's own declaration, none falling through."""
        return await self.one_or_none(self.statement().where(*_in_scope(AgentDeclaration, scope, agent)))

    # Written by the columns' own names, which the table keeps: `declared`, `declared_at`.
    async def put(self, scope: Scope, agent: str, declaration: dict[str, Any], sdk: str | None) -> AgentDeclaration:
        """Keep the declaration as the scope's, over the one before it."""
        values = {
            "org": scope.org,
            "env": scope.env,
            "holder": scope.holder,
            "agent": agent,
            "declared": declaration,
            "sdk": sdk,
            "declared_at": now(),
        }
        return await self.upsert(values, key=["org", "env", "holder", "agent"])


class WidgetRepository(Repository[AgentWidget]):
    """How the widget presents an agent."""

    model = AgentWidget

    async def find(self, org: str, env: Env, agent: str) -> AgentWidget | None:
        """The row, or None for the widget's own defaults."""
        return await self.one_or_none(
            self.statement().where(AgentWidget.org == org, AgentWidget.env == env, AgentWidget.agent == agent)
        )

    async def put(self, org: str, env: Env, agent: str, look: Mapping[str, Any]) -> AgentWidget:
        """Replace the look whole."""
        values = {"org": org, "env": env, "agent": agent, "set_at": now(), **look}
        return await self.upsert(values, key=["org", "env", "agent"])


# A melody's row is read without its clip: `audio` is a deferred column, and only `find_clip` asks for it.
class HoldAudioRepository(Repository[HoldAudio]):
    """What an agent plays while a tool runs."""

    model = HoldAudio

    async def find(self, org: str, env: Env, agent: str) -> HoldAudio | None:
        """The row, never its clip; None is the box's own melody."""
        return await self.one_or_none(
            self.statement().where(HoldAudio.org == org, HoldAudio.env == env, HoldAudio.agent == agent)
        )

    async def find_clip(self, org: str, env: Env, agent: str) -> bytes | None:
        """The clip the agent plays, when it plays one of its own."""
        statement = select(HoldAudio.audio).where(HoldAudio.org == org, HoldAudio.env == env, HoldAudio.agent == agent)
        audio = (await self.session.execute(statement)).scalar_one_or_none()
        return None if audio is None else bytes(audio)

    async def put(self, org: str, env: Env, agent: str, chosen: Mapping[str, Any]) -> HoldAudio:
        """Replace what is played, the columns named alone: the wait the org set stays."""
        values = {"org": org, "env": env, "agent": agent, "set_at": now(), **chosen}
        return await self.upsert(values, key=["org", "env", "agent"])

    # A row made for the wait plays the runtime's melody; one already there keeps what it plays.
    async def put_wait(self, org: str, env: Env, agent: str, after_s: float | None) -> HoldAudio:
        """Set how long the agent is quiet before its melody, and nothing else of the row."""
        made = insert(HoldAudio).values(
            org=org, env=env, agent=agent, played=HoldPlayed.default, after_s=after_s, set_at=now()
        )
        await self.session.execute(
            made.on_conflict_do_update(
                index_elements=["org", "env", "agent"],
                set_={"after_s": made.excluded.after_s, "set_at": made.excluded.set_at},
            )
        )
        kept = self.statement().where(HoldAudio.org == org, HoldAudio.env == env, HoldAudio.agent == agent)
        return await self.one(kept.execution_options(populate_existing=True))

    async def delete_of_org(self, org: str) -> int:
        """Forget every melody of the org; how many rows went."""
        return await self.change(delete(HoldAudio).where(HoldAudio.org == org))


# A line's row is read without its MP3: `audio` is a deferred column, and only `find_audio` asks for it.
class AgentLineRepository(Repository[AgentLine]):
    """The lines an agent's app has recorded in its voice, by the hash each is kept under."""

    model = AgentLine

    async def list_recorded(self, org: str, env: Env, agent: str, ids: Sequence[str]) -> Sequence[AgentLine]:
        """The ones of these already recorded, never their audio."""
        return await self.all(
            self.statement().where(
                AgentLine.org == org, AgentLine.env == env, AgentLine.agent == agent, AgentLine.id.in_(ids)
            )
        )

    async def find_audio(self, id_: str) -> bytes | None:
        """A line's MP3 by its id alone, whichever org recorded it: the id is the hash of what it holds."""
        audio = (await self.session.execute(select(AgentLine.audio).where(AgentLine.id == id_).limit(1))).scalar()
        return None if audio is None else bytes(audio)

    # Two requests may record the same line at once: the second finds it kept, and adds nothing.
    async def add_missing(self, lines: Sequence[Mapping[str, Any]]) -> None:
        """Keep the lines recorded now, each once."""
        if lines:
            made = insert(AgentLine).values([dict(line) for line in lines])
            await self.session.execute(made.on_conflict_do_nothing(index_elements=["org", "env", "agent", "id"]))


class AgentDocumentRepository(Repository[AgentDocument]):
    """The JSON documents an agent's app publishes for pages to read."""

    model = AgentDocument

    async def find(self, org: str, env: Env, agent: str, name: str) -> AgentDocument | None:
        """The document, or None while none was published under the name."""
        return await self.one_or_none(
            self.statement().where(
                AgentDocument.org == org,
                AgentDocument.env == env,
                AgentDocument.agent == agent,
                AgentDocument.name == name,
            )
        )

    async def put(self, org: str, env: Env, agent: str, name: str, body: dict[str, Any]) -> AgentDocument:
        """Publish the document whole, over the one before it."""
        values = {"org": org, "env": env, "agent": agent, "name": name, "body": body, "set_at": now()}
        return await self.upsert(values, key=["org", "env", "agent", "name"])


def _in_scope(model: Levelled, scope: Scope, agent: str) -> tuple[Any, ...]:
    return (model.org == scope.org, model.env == scope.env, model.holder == scope.holder, model.agent == agent)


def _in_scope_or_orgs(model: Levelled, scope: Scope, agent: str) -> tuple[Any, ...]:
    return (
        model.org == scope.org,
        model.env == scope.env,
        model.holder.in_((scope.holder, THE_ORGS_OWN)),
        model.agent == agent,
    )
