"""Every query on the agents tables: settings and lexicon versions, canaries, widgets, hold audio, prompts."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.models import (
    AgentCanary,
    AgentConfig,
    AgentDocument,
    AgentLine,
    AgentWidget,
    HoldAudio,
    Lexicon,
    Prompt,
)
from pinecall_runtime.kit.auth import THE_ORGS_OWN, Scope
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.kit.time import now

type VersionedModel = type[AgentConfig] | type[Lexicon]


class AgentConfigRepository(Repository[AgentConfig]):
    """The versions of an agent's settings in a scope."""

    model = AgentConfig

    async def history(self, scope: Scope, agent: str, *, limit: int) -> Sequence[AgentConfig]:
        """The scope's own versions, newest first."""
        return await self.all(
            self.statement()
            .where(*_scoped(AgentConfig, scope, agent))
            .order_by(AgentConfig.version.desc())
            .limit(limit)
        )

    async def at(self, scope: Scope, agent: str, version: int) -> AgentConfig | None:
        """One version: the holder's, or the org's it fell through to."""
        return await self.one_or_none(
            self.statement()
            .where(*_scoped_or_orgs(AgentConfig, scope, agent), AgentConfig.version == version)
            .order_by(AgentConfig.holder.desc())
            .limit(1)
        )

    async def newest_version(self, scope: Scope, agent: str) -> int:
        """The newest version number in the scope; 0 when none."""
        statement = select(func.coalesce(func.max(AgentConfig.version), 0)).where(*_scoped(AgentConfig, scope, agent))
        return int((await self.session.execute(statement)).scalar_one())

    async def put(self, scope: Scope, agent: str, config: dict[str, Any], author: str, note: str | None) -> AgentConfig:
        """The next version in the scope; the caller locked the scope and checked `if_version`."""
        version = await self.newest_version(scope, agent) + 1
        return await self.add(
            AgentConfig(
                org=scope.org,
                env=scope.env,
                holder=scope.holder,
                agent=agent,
                version=version,
                config=config,
                author=author,
                note=note,
            )
        )

    async def chain(
        self,
        scope: Scope,
        agent: str,
        *,
        standing: dict[str, tuple[int | None, int | None]],
        bucket: int | None,
        version: int | None,
    ) -> Sequence[AgentConfig]:
        """The newest row of each level (the holder's, the org's), nearest first, as a call is built from.

        `standing` is each level's canary (version, share); a call whose bucket is under the share
        runs the canary's version, every other the newest but that one; a `version` named is the
        holder's own, whatever canary stands.
        """
        rows = await self.all(
            self.statement()
            .where(*_scoped_or_orgs(AgentConfig, scope, agent))
            .order_by(AgentConfig.holder.desc(), AgentConfig.version.desc())
        )
        chosen: dict[str, AgentConfig] = {}
        for row in rows:
            if row.holder in chosen:
                continue
            canary_version, share = standing.get(row.holder, (None, None))
            if version is not None and row.holder == scope.holder:
                if row.version == version:
                    chosen[row.holder] = row
                continue
            if canary_version is None:
                chosen[row.holder] = row
                continue
            picked = bucket is not None and share is not None and bucket < share
            if (row.version == canary_version) == picked:
                chosen[row.holder] = row
        return [chosen[h] for h in sorted(chosen, reverse=True)]

    async def newest_per_agent(self, scope: Scope) -> Sequence[AgentConfig]:
        """Every agent's newest row at each level of the scope."""
        rows = await self.all(
            self.statement()
            .where(
                AgentConfig.org == scope.org,
                AgentConfig.env == scope.env,
                AgentConfig.holder.in_((scope.holder, THE_ORGS_OWN)),
            )
            .order_by(AgentConfig.agent, AgentConfig.holder.desc(), AgentConfig.version.desc())
        )
        seen: set[tuple[str, str]] = set()
        kept: list[AgentConfig] = []
        for row in rows:
            if (row.agent, row.holder) not in seen:
                seen.add((row.agent, row.holder))
                kept.append(row)
        return kept

    async def noted(
        self, scope: Scope, agent: str, versions: Sequence[int], since: datetime, until: datetime
    ) -> Sequence[AgentConfig]:
        """The versions named, and those set in [since, until), oldest first."""
        return await self.all(
            self.statement()
            .where(
                *_scoped_or_orgs(AgentConfig, scope, agent),
                or_(AgentConfig.version.in_(versions), (AgentConfig.set_at >= since) & (AgentConfig.set_at < until)),
            )
            .order_by(AgentConfig.version, AgentConfig.holder.desc())
        )


class LexiconRepository(Repository[Lexicon]):
    """The versions of an agent's lexicon in a scope."""

    model = Lexicon

    async def history(self, scope: Scope, agent: str, *, limit: int) -> Sequence[Lexicon]:
        """The scope's own versions, newest first."""
        return await self.all(
            self.statement().where(*_scoped(Lexicon, scope, agent)).order_by(Lexicon.version.desc()).limit(limit)
        )

    async def at(self, scope: Scope, agent: str, version: int) -> Lexicon | None:
        """One version: the holder's, or the org's it fell through to."""
        return await self.one_or_none(
            self.statement()
            .where(*_scoped_or_orgs(Lexicon, scope, agent), Lexicon.version == version)
            .order_by(Lexicon.holder.desc())
            .limit(1)
        )

    async def newest(self, scope: Scope, agent: str) -> Lexicon | None:
        """The newest row of the holder's level, else the org's."""
        return await self.one_or_none(
            self.statement()
            .where(*_scoped_or_orgs(Lexicon, scope, agent))
            .order_by(Lexicon.holder.desc(), Lexicon.version.desc())
            .limit(1)
        )

    async def newest_version(self, scope: Scope, agent: str) -> int:
        """The newest version number in the scope; 0 when none."""
        statement = select(func.coalesce(func.max(Lexicon.version), 0)).where(*_scoped(Lexicon, scope, agent))
        return int((await self.session.execute(statement)).scalar_one())

    async def put(
        self, scope: Scope, agent: str, said: dict[str, str], heard: list[str], author: str, note: str | None
    ) -> Lexicon:
        """The next version in the scope."""
        version = await self.newest_version(scope, agent) + 1
        return await self.add(
            Lexicon(
                org=scope.org,
                env=scope.env,
                holder=scope.holder,
                agent=agent,
                version=version,
                said=said,
                heard=heard,
                author=author,
                note=note,
            )
        )


class CanaryRepository(Repository[AgentCanary]):
    """A version of an agent's settings on a share of its calls; rows are only ever added."""

    model = AgentCanary

    async def standing(self, scope: Scope, agent: str) -> AgentCanary | None:
        """The scope's own newest row, cleared or not."""
        return await self.one_or_none(
            self.statement()
            .where(*_scoped(AgentCanary, scope, agent))
            .order_by(AgentCanary.set_at.desc(), AgentCanary.id.desc())
            .limit(1)
        )

    async def standing_per_level(
        self, scope: Scope, agent: str, *, at: datetime | None = None
    ) -> dict[str, AgentCanary]:
        """Each level's newest row (the holder's and the org's), at a moment or now."""
        statement = self.statement().where(*_scoped_or_orgs(AgentCanary, scope, agent))
        if at is not None:
            statement = statement.where(AgentCanary.set_at <= at)
        rows = await self.all(statement.order_by(AgentCanary.holder, AgentCanary.set_at.desc(), AgentCanary.id.desc()))
        found: dict[str, AgentCanary] = {}
        for row in rows:
            found.setdefault(row.holder, row)
        return found

    async def put(
        self,
        scope: Scope,
        agent: str,
        *,
        version: int | None,
        share: int | None,
        author: str,
        note: str | None,
        at: datetime,
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
                set_at=at,
            )
        )


class WidgetRepository(Repository[AgentWidget]):
    """How the widget presents an agent."""

    model = AgentWidget

    async def get(self, org: str, env: str, agent: str) -> AgentWidget | None:
        """The row, or None for the widget's own defaults."""
        return await self.one_or_none(
            self.statement().where(AgentWidget.org == org, AgentWidget.env == env, AgentWidget.agent == agent)
        )

    async def put(self, org: str, env: str, agent: str, **look: Any) -> AgentWidget:
        """Replace the look whole."""
        row = await self.get(org, env, agent)
        if row is None:
            return await self.add(AgentWidget(org=org, env=env, agent=agent, **look))
        return await self.update(row, set_at=now(), **look)


class HoldAudioRepository(Repository[HoldAudio]):
    """What an agent plays while a tool runs."""

    model = HoldAudio

    async def get(self, org: str, env: str, agent: str) -> HoldAudio | None:
        """The row; None is the box's own melody."""
        return await self.one_or_none(
            self.statement().where(HoldAudio.org == org, HoldAudio.env == env, HoldAudio.agent == agent)
        )

    async def put(self, org: str, env: str, agent: str, **chosen: Any) -> HoldAudio:
        """Replace what is played whole."""
        row = await self.get(org, env, agent)
        if row is None:
            return await self.add(HoldAudio(org=org, env=env, agent=agent, **chosen))
        return await self.update(row, set_at=now(), **chosen)


class AgentLineRepository(Repository[AgentLine]):
    """The lines an agent's app has recorded in its voice, by the hash each is kept under."""

    model = AgentLine

    async def get_many(self, org: str, env: str, agent: str, ids: Sequence[str]) -> dict[str, AgentLine]:
        """The ones of these already recorded, by id."""
        rows = await self.all(
            self.statement().where(
                AgentLine.org == org, AgentLine.env == env, AgentLine.agent == agent, AgentLine.id.in_(ids)
            )
        )
        return {row.id: row for row in rows}

    async def get_audio(self, id_: str) -> AgentLine | None:
        """A line by its id alone, whichever org recorded it: the id is the hash of what it holds."""
        return await self.one_or_none(self.statement().where(AgentLine.id == id_).limit(1))


class AgentDocumentRepository(Repository[AgentDocument]):
    """The JSON documents an agent's app publishes for pages to read."""

    model = AgentDocument

    async def get(self, org: str, env: str, agent: str, name: str) -> AgentDocument | None:
        """The document, or None while none was published under the name."""
        return await self.one_or_none(
            self.statement().where(
                AgentDocument.org == org,
                AgentDocument.env == env,
                AgentDocument.agent == agent,
                AgentDocument.name == name,
            )
        )

    async def put(self, org: str, env: str, agent: str, name: str, body: dict[str, Any]) -> AgentDocument:
        """Publish the document whole, over the one before it."""
        row = await self.get(org, env, agent, name)
        if row is None:
            return await self.add(AgentDocument(org=org, env=env, agent=agent, name=name, body=body))
        return await self.update(row, body=body, set_at=now())


class PromptRepository(Repository[Prompt]):
    """The blocks of prompt an org's calls were told, by hash."""

    model = Prompt

    async def keep(self, org: str, hash_: str, text: str) -> None:
        """Keep the text under its hash, once."""
        if await self.exists(self.statement().where(Prompt.org == org, Prompt.hash == hash_)):
            return
        await self.add(Prompt(org=org, hash=hash_, text=text), flush=True)

    async def texts_of(self, org: str, hashes: Sequence[str]) -> dict[str, str]:
        """The org's texts of these hashes, those it kept."""
        rows = await self.all(self.statement().where(Prompt.org == org, Prompt.hash.in_(hashes)))
        return {row.hash: row.text for row in rows}


class Agents:
    """The domain's repositories on one session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.configs = AgentConfigRepository(session)
        self.lexicons = LexiconRepository(session)
        self.canaries = CanaryRepository(session)
        self.widgets = WidgetRepository(session)
        self.hold_audio = HoldAudioRepository(session)
        self.prompts = PromptRepository(session)


def _scoped(model: VersionedModel | type[AgentCanary], scope: Scope, agent: str) -> tuple[Any, ...]:
    return (model.org == scope.org, model.env == scope.env, model.holder == scope.holder, model.agent == agent)


def _scoped_or_orgs(model: VersionedModel | type[AgentCanary], scope: Scope, agent: str) -> tuple[Any, ...]:
    return (
        model.org == scope.org,
        model.env == scope.env,
        model.holder.in_((scope.holder, THE_ORGS_OWN)),
        model.agent == agent,
    )
