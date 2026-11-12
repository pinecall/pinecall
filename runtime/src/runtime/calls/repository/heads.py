"""The call_log_head rows: a log's seq and seal, whose it is, the seal's lease, and what a call's head says of it."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from runtime.actor import THE_ORGS_OWN, Scope
from runtime.agents.settings import Versions
from runtime.calls.context import log_name
from runtime.calls.models import CallLogHead, Opener
from runtime.enums import Env
from runtime.kit.repository import Repository
from runtime.kit.time import now


@dataclass(frozen=True, slots=True)
class Claim:
    """What a call log is claimed with: its scope, the versions it was built on, who opened it."""

    scope: Scope
    versions: Versions = field(default_factory=Versions)
    # None for a dial placed before its worker opens it: the open says who.
    opened_by: Opener | None = None


@dataclass(frozen=True, slots=True)
class Claimant:
    """Whose a log is and the env it was claimed in; no env on an agent's own log."""

    org: str
    env: Env | None


@dataclass(frozen=True, slots=True)
class CallHead:
    """Where a call was opened: its scope, its agent, and what its head row says."""

    scope: Scope | None
    agent: str
    versions: Versions
    sealed: bool
    started_at: float | None
    # The entries its worker's writer sent: where a writer that takes the call over follows on.
    written: int
    # Who opened it; None for a call opened before the head said.
    opened_by: Opener | None = None


class HeadRepository(Repository[CallLogHead]):
    """One row per log: locked by the writer, read by everything that asks whose a call is."""

    model = CallLogHead

    async def find(self, log: str) -> CallLogHead | None:
        """The head by log name, or None for a log never written or claimed."""
        return await self.one_or_none(self.statement().where(CallLogHead.log == log))

    async def seq_of(self, log: str) -> int:
        """The last seq the log gave out, ephemerals counted; 0 for a log never written."""
        head = await self.find(log)
        return 0 if head is None else head.seq

    async def count_taken(self, log: str) -> int:
        """How many entries the log took from its writer's batches; 0 for none."""
        head = await self.find(log)
        return 0 if head is None else head.written

    async def is_sealed(self, log: str) -> bool:
        """Whether the log is sealed."""
        head = await self.find(log)
        return head is not None and head.sealed

    # Sealing a log nothing was written to is allowed: recovery may seal before the first entry.
    async def seal(self, call: str) -> None:
        """Seal the call's log; sealing twice changes nothing."""
        statement = insert(CallLogHead).values(log=call, call=call, sealed=True)
        statement = statement.on_conflict_do_update(index_elements=[CallLogHead.log], set_={"sealed": True})
        await self.session.execute(statement)

    # Taken by one gateway at a time, and only while the call is open; it runs out by itself. A
    # call that wrote nothing yet has no head: the lease makes it, as the seal does.
    async def lease_seal(self, call: str, seconds: float, by: str) -> bool:
        """Take the right to seal the call for so long; False when another holds it, or it ended."""
        until = now() + timedelta(seconds=seconds)
        statement = insert(CallLogHead).values(log=call, call=call, sealing_until=until, sealing_by=by)
        taken = statement.on_conflict_do_update(
            index_elements=[CallLogHead.log],
            set_={"sealing_until": statement.excluded.sealing_until, "sealing_by": statement.excluded.sealing_by},
            where=(~CallLogHead.sealed)
            & ((CallLogHead.sealing_until.is_(None)) | (CallLogHead.sealing_until < func.now())),
        ).returning(CallLogHead.log)
        return (await self.session.execute(taken)).scalar_one_or_none() is not None

    # The holder alone gives the lease back or renews it: a gateway that lost the race to the
    # lease cannot keep the winner's alive, and one that died stops renewing.
    async def renew_seal(self, call: str, seconds: float, by: str) -> None:
        """Hold the right to seal the call for so long again, while sealing it."""
        statement = (
            update(CallLogHead)
            .where(CallLogHead.log == call, ~CallLogHead.sealed, CallLogHead.sealing_by == by)
            .values(sealing_until=now() + timedelta(seconds=seconds))
        )
        await self.session.execute(statement)

    async def release_seal(self, call: str, by: str) -> None:
        """Give the right to seal back, after a seal that broke: the next request takes it."""
        statement = (
            update(CallLogHead)
            .where(CallLogHead.log == call, ~CallLogHead.sealed, CallLogHead.sealing_by == by)
            .values(sealing_until=None, sealing_by=None)
        )
        await self.session.execute(statement)

    # Until 2026-11 one `claim` took both and told them apart by a None: the org was said twice for
    # a call (beside its scope's), and never for an agent's log.
    async def claim_agent_log(self, agent: str, org: str) -> None:
        """Record the org of the agent's own log; the first claim stands."""
        await self._claim(log=log_name(None, agent), agent=agent, call=None, org=org, claim=None)

    async def claim_call(self, call: str, agent: str, claim: Claim) -> None:
        """Record the call's scope, the versions it was built on and who opened it; the first claim stands."""
        await self._claim(log=call, agent=agent, call=call, org=claim.scope.org, claim=claim)

    # The first claim wins, and it may come before the first entry.
    async def _claim(self, *, log: str, agent: str, call: str | None, org: str, claim: Claim | None) -> None:
        versions = Versions() if claim is None else claim.versions
        statement = insert(CallLogHead).values(
            log=log,
            agent=agent,
            call=call,
            org=org,
            env=None if claim is None else claim.scope.env,
            holder=None if claim is None else claim.scope.holder,
            config_version=versions.settings,
            lexicon_version=versions.lexicon,
            opened_by=None if claim is None else claim.opened_by,
        )
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=[CallLogHead.log],
            set_={
                "org": func.coalesce(CallLogHead.org, excluded.org),
                "env": func.coalesce(CallLogHead.env, excluded.env),
                "holder": func.coalesce(CallLogHead.holder, excluded.holder),
                "config_version": func.coalesce(CallLogHead.config_version, excluded.config_version),
                "lexicon_version": func.coalesce(CallLogHead.lexicon_version, excluded.lexicon_version),
                "opened_by": func.coalesce(CallLogHead.opened_by, excluded.opened_by),
            },
        )
        await self.session.execute(statement)

    # Whose a log is decides who may read it: asked box-wide, so another org's log reads as that
    # org's (a 404 to the asker) and never as nobody's (postgres.py, migration 0096).
    async def owner_of(self, log: str) -> str | None:
        """The org the log belongs to, or None while nobody claimed it. Read box-wide by the caller."""
        head = await self.find(log)
        return None if head is None else head.org

    async def claimant_of(self, log: str) -> Claimant | None:
        """Whose the log is and in which env, or None while nobody claimed it. Read box-wide by the caller."""
        head = await self.find(log)
        if head is None or head.org is None:
            return None
        return Claimant(org=head.org, env=head.env)

    # Head rows older than the env and holder columns read as production, the org's own.
    async def head_of_call(self, call: str) -> CallHead | None:
        """Where the call was opened, or None for one nobody wrote to or claimed. Read box-wide by the caller."""
        head = await self.one_or_none(self.statement().where(CallLogHead.log == call, CallLogHead.call.is_not(None)))
        if head is None:
            return None
        env = head.env or Env.production
        return CallHead(
            scope=None if head.org is None else Scope(head.org, env, head.holder or THE_ORGS_OWN),
            agent=head.agent or "",
            versions=Versions(settings=head.config_version, lexicon=head.lexicon_version),
            sealed=head.sealed,
            started_at=head.started_at,
            written=head.written,
            opened_by=head.opened_by,
        )

    # The operator's way back from a claim: an agent registered with the wrong key.
    # The copy a call was held in belongs to a member of the org it leaves: in the new org every
    # moved call is the org's own, else nobody there could read it. The org's own is "", as a claim
    # writes it: the lists match the holder by value, and null is nobody's.
    async def move_logs(self, agent: str, org: str) -> int:
        """Move every log of the agent to another org, as that org's own; how many moved."""
        statement = update(CallLogHead).where(CallLogHead.agent == agent).values(org=org, holder=THE_ORGS_OWN)
        return await self.change(statement)

    async def heads_of(self, calls: Sequence[str]) -> dict[str, CallLogHead]:
        """The heads of these calls, by call; a call never written has none."""
        if not calls:
            return {}
        statement = self.statement().where(CallLogHead.log.in_(list(calls)))
        return {str(head.log): head for head in await self.all(statement)}

    async def list_sealed(self, calls: Sequence[str]) -> set[str]:
        """The ones of these calls whose log is sealed, wherever it was sealed."""
        if not calls:
            return set()
        statement = select(CallLogHead.log).where(CallLogHead.log.in_(list(calls)), CallLogHead.sealed)
        return {str(log) for log in (await self.session.execute(statement)).scalars()}

    async def envs_of(self, calls: Sequence[str]) -> dict[str, Env]:
        """The env each of the calls was opened in, for the calls that have a log."""
        statement = select(CallLogHead.log, CallLogHead.env).where(
            CallLogHead.log.in_(list(calls)), CallLogHead.call.is_not(None)
        )
        return {str(log): env or Env.production for log, env in (await self.session.execute(statement)).all()}

    async def list_newest_calls(self, limit: int, *, agent: str | None = None) -> list[str]:
        """The newest calls of the box, or of one agent."""
        statement = select(CallLogHead.log).where(CallLogHead.call.is_not(None))
        if agent is not None:
            statement = statement.where(CallLogHead.agent == agent)
        statement = statement.order_by(CallLogHead.started_at.desc().nulls_last(), CallLogHead.log.desc()).limit(limit)
        return [str(log) for log in (await self.session.execute(statement)).scalars()]

    async def find_newest_live_call(self) -> str | None:
        """The newest call whose log is not sealed, or None."""
        statement = (
            select(CallLogHead.log)
            .where(CallLogHead.call.is_not(None), ~CallLogHead.sealed)
            .order_by(CallLogHead.started_at.desc().nulls_last(), CallLogHead.log.desc())
            .limit(1)
        )
        found = (await self.session.execute(statement)).scalar_one_or_none()
        return None if found is None else str(found)
