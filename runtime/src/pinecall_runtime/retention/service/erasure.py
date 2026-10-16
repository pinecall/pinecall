"""An erasure: a call's, a contact's, an agent's or an org's rows and recordings, and its trail."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import keys, orgs
from pinecall_runtime.calls import service as calls
from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Env, ErasureKind
from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.postgres import box_wide, unbounded
from pinecall_runtime.retention.repository import ErasureRepository
from pinecall_runtime.retention.schemas import ErasureRow

STILL_ON_A_CALL = "{contact} is on call {call} right now: erase them once it has ended"
STILL_ON_A_CALL_AS = "{agent} is on call {call} right now: erase it once the call has ended"


@dataclass(frozen=True, slots=True)
class Erased:
    """An erasure done: its trail row, and the calls it took, for a process that holds them."""

    trail: ErasureRow
    calls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Taking:
    """An erasure on its way: whose, what, who asked, and the rows gone so far."""

    org: str
    env: Env | None
    what: ErasureKind
    subject: str
    asked_by: str
    calls: Sequence[str]
    entries: int
    memories: int


# An erasure is unbounded: an org's logs are long to delete, and its recordings go inside the
# transaction, so a disk or a bucket that refuses leaves the rows in place and the erasure failed,
# not a trail that lies.
async def erase_call(
    session: AsyncSession, recordings: calls.Recordings, scope: Scope, call: str, *, by: str
) -> Erased:
    """Erase one call: its log, facts, tokens, the memories it taught, and its recording."""
    async with unbounded(session):
        repository = await _erasing(session)
        entries, memories = await _erase_logs(repository, [call], [call])
        taking = _Taking(scope.org, scope.env, ErasureKind.call, call, by, [call], entries, memories)
        return await _written(repository, recordings, taking)


async def erase_contact(
    session: AsyncSession, recordings: calls.Recordings, scope: Scope, contact: str, *, by: str
) -> Erased:
    """Erase a contact in the env: every call they were on and every fact kept of them."""
    async with unbounded(session):
        repository = await _erasing(session)
        found = await repository.calls_of_contact(scope.org, scope.env, contact)
        live = next((call for call, sealed in found if not sealed), None)
        if live is not None:
            raise Conflict(STILL_ON_A_CALL.format(contact=contact, call=live))
        erased = [call for call, _ in found]
        entries, taught = await _erase_logs(repository, erased, erased)
        kept = await repository.erase_contact(scope.org, scope.env, contact)
        taking = _Taking(scope.org, scope.env, ErasureKind.contact, contact, by, erased, entries, taught + kept)
        return await _written(repository, recordings, taking)


async def erase_org(session: AsyncSession, recordings: calls.Recordings, org: str, *, by: str) -> Erased:
    """Erase an org whole: every log it owns, every recording, then the org and what cascades."""
    async with unbounded(session):
        repository = await _erasing(session)
        heads = await repository.logs_of_org(org)
        logs = [head.log for head in heads]
        erased = [head.call for head in heads if head.call is not None]
        agents = sorted({head.agent for head in heads if head.agent is not None})
        entries, memories = await _erase_logs(repository, logs, erased)
        await repository.erase_org(org, agents)
        taking = _Taking(org, None, ErasureKind.org, org, by, erased, entries, memories)
        return await _written(repository, recordings, taking)


STILL_IN_USE = "org {slug} still has {what}: revoke its keys and remove its routes first"


# Never an org something still opens: a live key would answer for nobody, a route would ring nobody.
async def erase_unused_org(session: AsyncSession, recordings: calls.Recordings, named: str, *, by: str) -> Erased:
    """Erase the org the slug or id names, whole; Conflict while a key of it lives or a route names it."""
    with box_wide():
        org = await orgs.get_org(session, named)
        if any(key.revoked_at is None for key in await keys.list_keys(session, org.id)):
            raise Conflict(STILL_IN_USE.format(slug=org.slug, what="live keys"))
        for env in Env:
            if await channels.routes_of_org(session, org.id, env):
                raise Conflict(STILL_IN_USE.format(slug=org.slug, what="routes"))
        return await erase_org(session, recordings, org.id, by=by)


async def erase_agent(session: AsyncSession, recordings: calls.Recordings, org: str, agent: str, *, by: str) -> Erased:
    """Erase one agent of the org, both envs: its logs and recordings, and every row it owns."""
    async with unbounded(session):
        repository = await _erasing(session)
        heads = await repository.logs_of_agent(org, agent)
        live = next((head.call for head in heads if head.call is not None and not head.sealed), None)
        if live is not None:
            raise Conflict(STILL_ON_A_CALL_AS.format(agent=agent, call=live))
        logs = [head.log for head in heads]
        erased = [head.call for head in heads if head.call is not None]
        entries, memories = await _erase_logs(repository, logs, erased)
        await repository.erase_agent(org, agent)
        taking = _Taking(org, None, ErasureKind.agent, agent, by, erased, entries, memories)
        return await _written(repository, recordings, taking)


async def trail_of(session: AsyncSession, org: str) -> list[ErasureRow]:
    """The org's erasures, newest first."""
    return [ErasureRow.of(row) for row in await ErasureRepository(session).trail_of(org)]


async def _erasing(session: AsyncSession) -> ErasureRepository:
    repository = ErasureRepository(session)
    await repository.let_deletes_through()
    return repository


async def _erase_logs(repository: ErasureRepository, logs: Sequence[str], erased: Sequence[str]) -> tuple[int, int]:
    entries = await repository.erase_entries(logs)
    await repository.record_phone_calls(erased)
    return entries, await repository.erase_logs(logs, erased)


async def _written(repository: ErasureRepository, recordings: calls.Recordings, taking: _Taking) -> Erased:
    removed = await recordings.erase(taking.org, list(taking.calls))
    row = await repository.add_trail(
        org=taking.org,
        env=taking.env,
        what=taking.what,
        subject=taking.subject,
        asked_by=taking.asked_by,
        calls=len(taking.calls),
        entries=taking.entries,
        memories=taking.memories,
        recordings=removed,
    )
    return Erased(trail=ErasureRow.of(row), calls=tuple(taking.calls))
