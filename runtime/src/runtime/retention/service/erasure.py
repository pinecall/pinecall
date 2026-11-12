"""An erasure: a call's, a contact's, an agent's or an org's rows and recordings, and its trail."""

from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import THE_ORGS_OWN, Actor, Scope
from runtime.agents import service as agents
from runtime.alerts import service as alerts
from runtime.calls import service as calls
from runtime.calls.log import Logs
from runtime.calls.recordings import Recordings
from runtime.compliance import service as compliance
from runtime.enums import Env, ErasureKind
from runtime.evals import service as evals
from runtime.exceptions import Conflict, NotFound
from runtime.insights import service as insights
from runtime.kit.commit import run_after_commit
from runtime.knowledge import service as knowledge
from runtime.live import service as live
from runtime.livekit import Servers
from runtime.postgres import without_timeouts
from runtime.providers import service as providers
from runtime.retention.models import Erasure
from runtime.retention.repository.erasures import ErasureRepository
from runtime.signin import service as signin
from runtime.telephony import service as telephony

NO_SUCH_CALL = "no call {call} in this key's org and env"
STILL_LIVE = "call {call} is still live: erase it once it has ended"
STILL_ON_A_CALL = "{contact} is on call {call} right now: erase them once it has ended"
STILL_ON_A_CALL_AS = "{agent} is on call {call} right now: erase it once the call has ended"
STILL_IN_USE = "org {slug} still has {what}: revoke its keys and remove its routes first"
NOT_HELD = "agent {slug} is held right now: stop it, move it, and start it again"


class Holders(Protocol):
    """The apps holding each agent now, as the live side keeps them."""

    def is_held(self, org: str, slug: str) -> bool:
        """Whether a process holds the agent in the org now, in either env."""
        ...


@dataclass(frozen=True, slots=True)
class Erasing:
    """What an erasure reaches outside the database: the recordings' store, and the logs open in this process."""

    recordings: Recordings
    logs: Logs


@dataclass(frozen=True, slots=True)
class _Taken:
    """What an erasure took so far: whose, what, who asked, and the rows gone."""

    org: str
    env: Env | None
    what: ErasureKind
    subject: str
    asked_by: str
    owned: Sequence[calls.OwnedLog]
    entries: int
    memories: int


# ── the org's own ──


# The org's own calls, in the key's env; a holder's call is the holder's or the org's to erase.
async def erase_own_call(session: AsyncSession, erasing: Erasing, actor: Actor, call: str) -> Erasure:
    """Erase one call the key may erase: its log, facts, tokens, the memories it taught and its recording."""
    kept = await calls.find_head(session, call)
    if kept is None or kept.scope is None or not _sees_to_erase(actor.scope, kept.scope):
        raise NotFound(NO_SUCH_CALL.format(call=call))
    accounts.check_agent(actor, kept.agent)
    if not kept.sealed:
        raise Conflict(STILL_LIVE.format(call=call))
    return await erase_call(session, erasing, kept.scope, call, by=actor.asked_by)


# An erasure runs with no statement timeout: an org's logs are long to delete, and its recordings go
# inside the transaction, so a disk or a bucket that refuses leaves the rows in place and the erasure
# failed, not a trail that lies.
async def erase_call(session: AsyncSession, erasing: Erasing, scope: Scope, call: str, *, by: str) -> Erasure:
    """Erase one call: its log, facts, tokens, the memories it taught, and its recording."""
    async with without_timeouts(session):
        owned = [calls.OwnedLog(log=call, call=call, agent=None, sealed=True)]
        entries, memories = await _erase_logs(session, owned)
        taken = _Taken(scope.org, scope.env, ErasureKind.call, call, by, owned, entries, memories)
        return await _write_trail(session, erasing, taken)


# A person's "delete my data": what they said on every call of the env, and what was kept of them.
async def erase_contact(session: AsyncSession, erasing: Erasing, scope: Scope, contact: str, *, by: str) -> Erasure:
    """Erase a contact in the env: every call they were on and every fact kept of them."""
    async with without_timeouts(session):
        owned = await calls.list_logs_of_contact(session, scope.org, scope.env, contact)
        live_now = next((log.call for log in owned if not log.sealed), None)
        if live_now is not None:
            raise Conflict(STILL_ON_A_CALL.format(contact=contact, call=live_now))
        entries, taught = await _erase_logs(session, owned)
        kept = await knowledge.forget(session, Scope(scope.org, scope.env), contact)
        await ErasureRepository(session).delete_of_contact(scope.org, scope.env, contact)
        taken = _Taken(scope.org, scope.env, ErasureKind.contact, contact, by, owned, entries, taught + kept)
        return await _write_trail(session, erasing, taken)


# ── the operator's ──


# An agent that is not the org's (run once under its key, a test, a copy) taken out whole, both envs.
# Refused while a process of the org holds it, which would only register it again. Its numbers are let
# go by their owner, which takes them off the SFU too: deleted as rows, a number stayed admitted there
# and nobody else could import it.
async def erase_agent(
    session: AsyncSession, erasing: Erasing, servers: Servers, holders: Holders, named: str, agent: str, *, by: str
) -> Erasure:
    """Erase one agent of the org, both envs: its logs and recordings, and every row it owns."""
    org = (await accounts.get_org(session, named)).id
    if holders.is_held(org, agent):
        raise Conflict(NOT_HELD.format(slug=agent))
    async with without_timeouts(session):
        owned = await calls.list_logs_of_agent(session, org, agent)
        live_now = next((log.call for log in owned if log.call is not None and not log.sealed), None)
        if live_now is not None:
            raise Conflict(STILL_ON_A_CALL_AS.format(agent=agent, call=live_now))
        entries, memories = await _erase_logs(session, owned)
        await telephony.release_numbers_of(session, servers, org, agent=agent)
        await evals.delete_runs(session, org, agent)
        await accounts.drop_agent_from_members(session, org, agent)
        await ErasureRepository(session).delete_of_agent(org, agent)
        taken = _Taken(org, None, ErasureKind.agent, agent, by, owned, entries, memories)
        return await _write_trail(session, erasing, taken)


# Never an org something still opens: a live key would answer for nobody, a route would ring nobody.
async def erase_unused_org(session: AsyncSession, erasing: Erasing, named: str, *, by: str) -> Erasure:
    """Erase the org the slug or id names, whole; Conflict while a key of it lives or a route names it."""
    org = await accounts.get_org(session, named)
    if any(key.revoked_at is None for key in await accounts.list_keys(session, org.id)):
        raise Conflict(STILL_IN_USE.format(slug=org.slug, what="live keys"))
    for env in Env:
        if await telephony.list_routes(session, org.id, env):
            raise Conflict(STILL_IN_USE.format(slug=org.slug, what="routes"))
    return await erase_org(session, erasing, org.id, by=by)


# What names the org with no cascading key to it is erased by its owner's own verb, each named by the
# table it erases (`Kept.erased_by`); then the org's row goes, and what hangs off it with it.
async def erase_org(session: AsyncSession, erasing: Erasing, org: str, *, by: str) -> Erasure:
    """Erase an org whole: every log it owns, every recording, then the org and what cascades."""
    async with without_timeouts(session):
        owned = await calls.list_logs_of_org(session, org)
        entries, memories = await _erase_logs(session, owned)
        await evals.delete_runs(session, org)
        await agents.forget_melodies(session, org)
        await calls.delete_reads(session, org)
        await live.delete_tokens(session, org)
        await compliance.delete_recording_keys(session, org)
        await alerts.forget_webhook(session, org)
        await providers.forget_telemetry(session, org)
        await signin.delete_proofs(session, org)
        await accounts.delete_keys(session, org)
        await accounts.delete_org(session, org)
        await accounts.delete_orphans(session)
        taken = _Taken(org, None, ErasureKind.org, org, by, owned, entries, memories)
        return await _write_trail(session, erasing, taken)


async def list_trail(session: AsyncSession, org: str) -> Sequence[Erasure]:
    """The org's erasures, newest first."""
    return await ErasureRepository(session).list_trail(org)


# ── private ──


def _sees_to_erase(where: Scope, owner: Scope) -> bool:
    same = where.org == owner.org and where.env == owner.env
    return same and owner.holder in (THE_ORGS_OWN, where.holder)


# The calls' own rows first, by their owner and in the order their trigger needs; then what the calls
# taught, the last failure a tool's day names, and every row another table declares as the calls'.
async def _erase_logs(session: AsyncSession, owned: Sequence[calls.OwnedLog]) -> tuple[int, int]:
    erased = [log.call for log in owned if log.call is not None]
    entries = await calls.erase_logs(session, owned)
    memories = await knowledge.forget_taught(session, erased)
    await insights.forget_calls(session, erased)
    await ErasureRepository(session).delete_of_calls([log.log for log in owned], erased)
    return entries, memories


# The trail is written last, in the transaction that erased: no trail of an erasure that failed. The
# process that holds an erased call's log forgets it once the erasure is committed.
async def _write_trail(session: AsyncSession, erasing: Erasing, taken: _Taken) -> Erasure:
    erased = [log.call for log in taken.owned if log.call is not None]
    removed = await erasing.recordings.erase(taken.org, erased)
    row = Erasure(
        org=taken.org,
        env=taken.env,
        what=taken.what,
        subject=taken.subject,
        asked_by=taken.asked_by,
        calls=len(erased),
        entries=taken.entries,
        memories=taken.memories,
        recordings=removed,
    )
    for call in erased:
        run_after_commit(session, partial(erasing.logs.forget, call))
    return await ErasureRepository(session).add(row)
