"""A password: counted three ways, the right one opens a key, any wrong one says one sentence for all."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service import actor, invitations
from runtime.accounts.service.key_cache import KeyCache
from runtime.enums import Role
from runtime.exceptions import Forbidden
from runtime.platform.service.attempts import TooManyAttempts
from runtime.signin.service.passwords import (
    PASSWORD_TRIES_A_PLACE,
    PASSWORD_TRIES_AN_ADDRESS,
    SIGN_IN_TRIES,
    NobodyAnswers,
    PasswordSignIn,
    PasswordThrottle,
    sign_in_with_password,
)
from tests.conftest import A_PASSWORD, Tenant, make_tenant, needs_the_database

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


# ── the password signed in with ──


async def signed_in(sessions: async_sessionmaker[AsyncSession], asking: PasswordSignIn) -> str:
    """The secret of the key a password opens, asked from a place of the test's own."""
    async with sessions.begin() as session:
        issued = await sign_in_with_password(session, PasswordThrottle(sessions), asking, client=a_place())
    return issued.secret


async def test_the_right_password_opens_a_key_of_the_persons_org(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The admin's address and password sign them in, with a key that verifies to them."""
    secret = await signed_in(sessions, PasswordSignIn(email=f"admin@{tenant.slug}.test", password=A_PASSWORD))
    async with sessions.begin() as session:
        verified = await actor.verify_key(session, secret)
    assert verified is not None
    assert verified.membership is not None and verified.membership.id == tenant.member


@pytest.mark.parametrize("who", ["wrong password", "nobody's address"])
async def test_a_wrong_password_and_an_unknown_address_get_the_same_sentence(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, who: str
) -> None:
    """Nobody learns who is a member: both refusals read alike."""
    email = f"admin@{tenant.slug}.test" if who == "wrong password" else f"nobody@{tenant.slug}.test"
    with pytest.raises(NobodyAnswers, match="nobody answers to that email and password"):
        await signed_in(sessions, PasswordSignIn(email=email, password="not-it-at-all"))


async def test_a_person_invited_elsewhere_with_an_unproven_address_is_told_to_open_the_link(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache, tenant: Tenant
) -> None:
    """A link an admin handed over proves no address: the password they have does not seat them elsewhere."""
    email = f"later@{tenant.slug}.test"
    second = await make_tenant(sessions)
    invitee = invitations.Invitee(email, "Later", Role.qa)
    async with sessions.begin() as session:
        first = await invitations.invite(session, tenant.org, invitee, held_to_seats=False)
    async with sessions.begin() as session:
        assert await invitations.accept_link(session, key_cache, first.token, A_PASSWORD, 8) is not None
    async with sessions.begin() as session:
        await invitations.invite(session, second.org, invitee, held_to_seats=False)
    with pytest.raises(Forbidden, match="has not accepted their invitation yet"):
        await signed_in(sessions, PasswordSignIn(email=email, password=A_PASSWORD, org=second.slug))
