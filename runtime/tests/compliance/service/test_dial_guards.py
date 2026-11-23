"""The guards a call or a text placed cold passes: its shape, a stranger, the hours, the pace; each refusal kept."""

import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.compliance.service import dial_guards, policy
from runtime.compliance.service.dial_guards import DialAsk, Guards
from runtime.compliance.service.policy import Hours, Policy
from runtime.enums import Channel, Env
from runtime.exceptions import Forbidden, TooManyRequests, ValidationError
from tests.conftest import Tenant, needs_the_database

HER_PHONE = "+59899000001"


def a_dial(tenant: Tenant, to: str = HER_PHONE, call: str | None = None) -> DialAsk:
    """The tenant's agent dialling the number in the sandbox, asked by its admin, now."""
    return DialAsk(
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
    assert dial_guards.destination_of("+59899000001") == "+59899000001"


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
        dial_guards.destination_of(number)


# ── the org's guards ──


@needs_the_database
async def test_an_org_nobody_set_guards_for_has_the_defaults_and_a_write_replaces_them_whole(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The defaults until an operator writes the org's guards; then exactly what was written."""
    async with sessions() as session:
        assert await dial_guards.guards_of(session, tenant.org) == Guards()
    async with sessions.begin() as session:
        await dial_guards.put_guards(session, tenant.org, Guards(dial_anywhere=True, per_minute=2))
    async with sessions() as session:
        assert await dial_guards.guards_of(session, tenant.org) == Guards(dial_anywhere=True, per_minute=2)
    async with sessions.begin() as session:
        with pytest.raises(ValidationError, match="per_day is never below zero"):
            await dial_guards.put_guards(session, tenant.org, Guards(per_day=-1))


@needs_the_database
async def test_a_stranger_is_never_rung_until_an_operator_lets_the_org_dial_anywhere(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A call back goes back to somebody: a number that never reached the org is refused, and written down."""
    dial = a_dial(tenant)
    async with sessions.begin() as session:
        with pytest.raises(Forbidden, match="never called or wrote to this org"):
            await dial_guards.guard_dial(session, sessions, dial, nobody)
    async with sessions() as session:
        written = await dial_guards.list_dials_to(session, HER_PHONE, dial.at - timedelta(minutes=1))
    assert [row.refused for row in written if row.org == tenant.org] == [dial_guards.STRANGER]
    async with sessions.begin() as session:
        await dial_guards.put_guards(session, tenant.org, Guards(dial_anywhere=True))
    async with sessions.begin() as session:
        await dial_guards.guard_dial(session, sessions, a_dial(tenant), nobody)


@needs_the_database
async def test_the_org_dialling_past_its_minute_is_held_back(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """One dial a minute allowed: the second within it is refused, naming the pace."""
    async with sessions.begin() as session:
        await dial_guards.put_guards(session, tenant.org, Guards(per_minute=1))
    async with sessions.begin() as session:
        await dial_guards.guard_dial(session, sessions, a_dial(tenant), anybody)
    async with sessions.begin() as session:
        with pytest.raises(TooManyRequests, match="1 numbers in the last minute of its 1"):
            await dial_guards.guard_dial(session, sessions, a_dial(tenant, to="+59899000002"), anybody)


def test_an_address_is_reached_lowercased_and_never_taken_for_a_number() -> None:
    """On the channel `email` the contact is an address; on every other, a number in E.164."""
    assert dial_guards.destination_of(" Ana@Example.org ", Channel.email) == "ana@example.org"
    with pytest.raises(ValidationError, match="in E\\.164 form"):
        dial_guards.destination_of("ana@example.org")
    with pytest.raises(ValidationError, match="one @"):
        dial_guards.destination_of(HER_PHONE, Channel.email)


# An address names no zone: the org's hours are kept in its agent's. Until 2026-11-23 its "zones" were
# asked of libphonenumber, which raises on anything that is not a number.
@needs_the_database
async def test_an_address_is_held_to_the_orgs_hours_in_its_agents_zone_and_with_none_is_written_to_by_nobody(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    async with sessions.begin() as session:
        await policy.put_policy(session, tenant.org, Policy(calling_hours=Hours(9, 17)), by=tenant.member)
    morning, night = datetime(2026, 11, 23, 10, 0, tzinfo=UTC), datetime(2026, 11, 23, 22, 0, tzinfo=UTC)

    def an_email(at: datetime, zone: str | None) -> DialAsk:
        dial = replace(a_dial(tenant, to="ana@example.org"), scope=Scope(tenant.org, Env.production), at=at)
        return replace(dial, shown="help@acme.example", channel=Channel.email, zone=zone)

    async with sessions.begin() as session:
        with pytest.raises(Forbidden, match="is an address, held to its agent's own `timezone`"):
            await dial_guards.guard_dial(session, sessions, an_email(morning, None), anybody)
    async with sessions.begin() as session:
        with pytest.raises(Forbidden, match="outside the hours"):
            await dial_guards.guard_dial(session, sessions, an_email(night, "UTC"), anybody)
    async with sessions.begin() as session:
        await dial_guards.guard_dial(session, sessions, an_email(morning, "UTC"), anybody)
