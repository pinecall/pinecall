"""The dial guards a call placed cold passes: its shape, a stranger, the pace; each refusal written down."""

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import Forbidden, TooManyRequests, ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.telephony.service import dial_policy
from pinecall_runtime.telephony.service.dial_policy import Dial, Guards
from tests.conftest import Tenant, needs_the_database

HER_PHONE = "+59899000001"


def a_dial(tenant: Tenant, to: str = HER_PHONE, call: str | None = None) -> Dial:
    """The tenant's agent dialling the number in the sandbox, asked by its admin, now."""
    return Dial(
        scope=Scope(tenant.org, Env.sandbox),
        agent="recepcion",
        to=to,
        shown="+15550100133",
        asked_by=tenant.member,
        call=call or f"call_{secrets.token_hex(6)}",
        at=datetime.now(UTC),
    )


async def anybody(_number: str) -> bool:
    """Every number has called the org before."""
    return True


async def nobody(_number: str) -> bool:
    """No number ever called the org."""
    return False


# ── the shape, pure ──


def test_a_number_with_its_country_code_is_dialled_as_written() -> None:
    """An E.164 number of a country passes as it is."""
    assert dial_policy.destination_of("+59899000001") == "+59899000001"


@pytest.mark.parametrize(
    ("number", "why"),
    [
        ("+8816000000", "satellite or global-service"),
        ("+5981", "shorter than a number anybody calls from"),
    ],
)
def test_a_number_nobody_should_ring_is_refused_by_its_shape(number: str, why: str) -> None:
    """Satellite ranges, which cost a fortune, and numbers too short to be a line, never ring."""
    with pytest.raises(ValidationError, match=why):
        dial_policy.destination_of(number)


# ── the org's guards ──


@needs_the_database
async def test_an_org_nobody_set_guards_for_has_the_defaults_and_a_write_replaces_them_whole(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The defaults until an operator writes the org's guards; then exactly what was written."""
    async with sessions() as session:
        assert await dial_policy.guards_of(session, tenant.org) == Guards()
    async with sessions.begin() as session:
        await dial_policy.put_guards(session, tenant.org, Guards(dial_anywhere=True, per_minute=2))
    async with sessions() as session:
        assert await dial_policy.guards_of(session, tenant.org) == Guards(dial_anywhere=True, per_minute=2)
    async with sessions.begin() as session:
        with pytest.raises(ValidationError, match="per_day is never below zero"):
            await dial_policy.put_guards(session, tenant.org, Guards(per_day=-1))


@needs_the_database
async def test_a_stranger_is_never_rung_until_an_operator_lets_the_org_dial_anywhere(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A call back goes back to somebody: a number that never reached the org is refused, and written down."""
    dial = a_dial(tenant)
    async with sessions.begin() as session:
        with pytest.raises(Forbidden, match="never called or wrote to this org"):
            await dial_policy.guard_dial(session, dial, nobody)
    async with sessions() as session:
        written = await dial_policy.dials_to(session, HER_PHONE, dial.at - timedelta(minutes=1))
    assert [row.refused for row in written if row.org == tenant.org] == [dial_policy.STRANGER]
    async with sessions.begin() as session:
        await dial_policy.put_guards(session, tenant.org, Guards(dial_anywhere=True))
    async with sessions.begin() as session:
        await dial_policy.guard_dial(session, a_dial(tenant), nobody)


@needs_the_database
async def test_the_org_dialling_past_its_minute_is_held_back(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """One dial a minute allowed: the second within it is refused, naming the pace."""
    async with sessions.begin() as session:
        await dial_policy.put_guards(session, tenant.org, Guards(per_minute=1))
    async with sessions.begin() as session:
        await dial_policy.guard_dial(session, a_dial(tenant), anybody)
    async with sessions.begin() as session:
        with pytest.raises(TooManyRequests, match="1 numbers in the last minute of its 1"):
            await dial_policy.guard_dial(session, a_dial(tenant, to="+59899000002"), anybody)
