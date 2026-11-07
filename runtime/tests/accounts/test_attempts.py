"""A password tried is counted three ways, and whichever count runs out says the same sentence."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service.attempts import (
    PASSWORD_TRIES_A_PLACE,
    PASSWORD_TRIES_AN_ADDRESS,
    SIGN_IN_TRIES,
    PasswordThrottle,
    TooManyAttempts,
)
from tests.conftest import needs_the_database

pytestmark = needs_the_database


# The suites share one database and run at once, and every count sweeps the rows older than the
# window: a clock of this test's own would sweep another test's rows, so the throttle keeps the
# real one and each test owns its names.
def a_place() -> str:
    return f"203.0.113.{uuid4().hex[:6]}"


async def test_one_address_from_one_place_is_five_a_minute(sessions: async_sessionmaker[AsyncSession]) -> None:
    throttle, place = PasswordThrottle(sessions), a_place()
    for _ in range(SIGN_IN_TRIES):
        await throttle.check(place, "ana@clinica.test", "clinica-norte")
    with pytest.raises(TooManyAttempts, match="try again in a minute"):
        await throttle.check(place, "ana@clinica.test", "clinica-norte")


async def test_many_addresses_from_one_place_run_out_the_places_budget(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Credential stuffing tries one password at many addresses: each is under five, the place is not."""
    throttle, place = PasswordThrottle(sessions), a_place()
    for n in range(PASSWORD_TRIES_A_PLACE):
        await throttle.check(place, f"person{n}@stuffed.test")
    with pytest.raises(TooManyAttempts):
        await throttle.check(place, "one-more@stuffed.test")


async def test_one_address_from_many_places_runs_out_the_addresss_budget(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A spread attack on one account comes from many places: each is under five, the address is not."""
    throttle, address = PasswordThrottle(sessions), f"{uuid4().hex[:8]}@clinica.test"
    for n in range(PASSWORD_TRIES_AN_ADDRESS):
        await throttle.check(f"192.0.2.{n}", address)
    with pytest.raises(TooManyAttempts):
        await throttle.check("192.0.2.250", address)


async def test_the_sentence_names_no_count(sessions: async_sessionmaker[AsyncSession]) -> None:
    """Which budget ran out would say how the box counts; the refusal says only the address and the minute."""
    throttle, place = PasswordThrottle(sessions), a_place()
    for n in range(PASSWORD_TRIES_A_PLACE):
        await throttle.check(place, f"p{n}@quiet.test")
    with pytest.raises(TooManyAttempts) as refused:
        await throttle.check(place, "last@quiet.test")
    assert str(refused.value) == "too many attempts for last@quiet.test: try again in a minute"
