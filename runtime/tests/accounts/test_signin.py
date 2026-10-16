"""Signing in with a password: the right one opens a key, any wrong one says one sentence for all."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.service import keys, members, signin
from pinecall_runtime.enums import Role
from pinecall_runtime.exceptions import Forbidden
from tests.conftest import A_PASSWORD, Tenant, make_tenant, needs_the_database

pytestmark = needs_the_database


async def test_the_right_password_opens_a_key_of_the_persons_org(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The admin's address and password sign them in, with a key that verifies to them."""
    asking = signin.PasswordSignIn(email=f"admin@{tenant.slug}.test", password=A_PASSWORD)
    async with sessions.begin() as session:
        signed = await signin.sign_in_with_password(session, asking)
    async with sessions.begin() as session:
        verified = await keys.verify_key(session, signed.secret)
    assert verified is not None
    assert verified[1] is not None and verified[1].id == tenant.member


@pytest.mark.parametrize("who", ["wrong password", "nobody's address"])
async def test_a_wrong_password_and_an_unknown_address_get_the_same_sentence(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, who: str
) -> None:
    """Nobody learns who is a member: both refusals read alike."""
    email = f"admin@{tenant.slug}.test" if who == "wrong password" else f"nobody@{tenant.slug}.test"
    async with sessions.begin() as session:
        with pytest.raises(signin.NobodyAnswers, match="nobody answers to that email and password"):
            await signin.sign_in_with_password(session, signin.PasswordSignIn(email=email, password="not-it-at-all"))


async def test_a_person_invited_elsewhere_with_an_unproven_address_is_told_to_open_the_link(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A link an admin handed over proves no address: the password they have does not seat them elsewhere."""
    email = f"later@{tenant.slug}.test"
    second = await make_tenant(sessions)
    async with sessions.begin() as session:
        first = await members.invite(session, tenant.org, members.Invitee(email, "Later", Role.qa), seats=None)
    async with sessions.begin() as session:
        assert await members.accept_link(session, first.token, A_PASSWORD, 8) is not None
    async with sessions.begin() as session:
        await members.invite(session, second.org, members.Invitee(email, "Later", Role.qa), seats=None)
    asking = signin.PasswordSignIn(email=email, password=A_PASSWORD, org=second.org)
    async with sessions.begin() as session:
        with pytest.raises(Forbidden, match="has not accepted their invitation yet"):
            await signin.sign_in_with_password(session, asking)
