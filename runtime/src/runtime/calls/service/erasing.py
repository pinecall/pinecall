"""What an erasure takes of the calls: the logs a subject owns, and each log's rows, its phone call recorded first."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.calls.repository.erasure import ErasureRepository
from runtime.calls.repository.records import RecordRepository
from runtime.enums import Env

# An erased phone call's record is kept for a carrier's traceback this long.
RECORDS_KEPT_S = 730 * 86_400


@dataclass(frozen=True, slots=True)
class OwnedLog:
    """One log a subject of an erasure owns: its call, when it is a call's, its agent, and whether it is sealed."""

    log: str
    call: str | None
    agent: str | None
    sealed: bool


async def list_logs_of_org(session: AsyncSession, org: str) -> list[OwnedLog]:
    """Every log of the org: its calls, and its agents' own logs, which carry no call."""
    return [_own(head.log, head.call, head.agent, head.sealed) for head in await _logs(session).list_of_org(org)]


async def list_logs_of_agent(session: AsyncSession, org: str, agent: str) -> list[OwnedLog]:
    """Every log of one agent of the org, both envs and every holder."""
    found = await _logs(session).list_of_agent(org, agent)
    return [_own(head.log, head.call, head.agent, head.sealed) for head in found]


async def list_logs_of_contact(session: AsyncSession, org: str, env: Env, contact: str) -> list[OwnedLog]:
    """Every call of the contact in the env."""
    found = await _logs(session).list_of_contact(org, env, contact)
    return [_own(head.log, head.call, head.agent, head.sealed) for head in found]


# In this order: a phone call's numbers and times are written down before its facts go, and the
# entries go before the heads (`ErasureRepository.delete_logs`).
async def erase_logs(session: AsyncSession, owned: Sequence[OwnedLog]) -> int:
    """Erase the logs whole: entries, what they sealed aside, heads, facts and openings; how many entries went."""
    calls = [log.call for log in owned if log.call is not None]
    await RecordRepository(session).record_phone_calls(calls)
    return await _logs(session).delete_logs([log.log for log in owned], calls)


async def forget_records(session: AsyncSession, now: float) -> int:
    """Forget the records of erased phone calls more than two years old; how many."""
    return await RecordRepository(session).delete_before(now - RECORDS_KEPT_S)


def _logs(session: AsyncSession) -> ErasureRepository:
    return ErasureRepository(session)


def _own(log: str, call: str | None, agent: str | None, sealed: bool) -> OwnedLog:
    return OwnedLog(log=log, call=call, agent=agent, sealed=sealed)
