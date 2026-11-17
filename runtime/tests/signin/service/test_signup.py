"""A sign-up founds an org, its admin proven and keyed; an address it may not take is mailed a note, not a code."""

import os
import secrets

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.accounts.service import orgs, people
from runtime.accounts.service.key_cache import KeyCache
from runtime.enums import MemberStatus, Role
from runtime.kit.crypto import Vault
from runtime.mail import service as mail
from runtime.platform import service as platform
from runtime.signin.service import signup
from runtime.signin.service.codes import LoginCodes
from tests.conftest import A_PASSWORD, Tenant, needs_the_database


@needs_the_database
async def test_a_newcomers_org_is_made_with_no_password_and_a_verified_admin(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache
) -> None:
    """What POST /v1/signup/google founds: the org, its admin seated verified, a key and the console's code."""
    email, slug = f"dana-{secrets.token_hex(3)}@gmail.test", f"dana-{secrets.token_hex(4)}"
    codes = LoginCodes(sessions, Vault(os.environ["PINECALL_VAULT_KEY"]))
    async with sessions.begin() as session:
        founding = signup.Founding(email, slug, "Dana", "Dana's workspace", hashed=None)
        founded = await signup.found_org(session, key_cache, codes, founding)
        assert (founded.slug, founded.member.status, founded.member.verified) == (slug, MemberStatus.active, True)
        assert founded.code
    async with sessions() as session:
        person = await people.find_person(session, email)
        assert person is not None and person.password_hash is None
        assert (await orgs.get_org(session, slug)).name == "Dana's workspace"


# ── an address a sign-up may not take ──


async def noted(
    sessions: async_sessionmaker[AsyncSession], email: str, password: str = "another-password"
) -> mail.Email | None:
    """What a sign-up for the address is mailed instead of its code."""
    async with sessions() as session:
        asking = signup.Asking(email, "Somebody", password)
        return await signup.note_instead_of_a_code(session, asking, await platform.get_brand(session))


@needs_the_database
async def test_an_address_nobody_knows_is_mailed_its_code(sessions: async_sessionmaker[AsyncSession]) -> None:
    assert await noted(sessions, f"nobody-{secrets.token_hex(4)}@gmail.test") is None


# 2026-11-17: a founder who had signed up with Google filled the form with the same address and was
# mailed "You have an invitation waiting". Nobody had invited them: a seat with no password was read
# as an invitation, whatever its status.
@needs_the_database
async def test_a_founder_who_came_in_with_google_is_told_they_have_an_account(
    sessions: async_sessionmaker[AsyncSession], key_cache: KeyCache
) -> None:
    email, slug = f"dana-{secrets.token_hex(3)}@gmail.test", f"dana-{secrets.token_hex(4)}"
    codes = LoginCodes(sessions, Vault(os.environ["PINECALL_VAULT_KEY"]))
    async with sessions.begin() as session:
        await signup.found_org(session, key_cache, codes, signup.Founding(email, slug, "Dana", "Dana's", hashed=None))
    note = await noted(sessions, email)
    assert note is not None and note.subject.startswith("You already have an account")
    assert "with Google" in note.text and "invit" not in note.text


@needs_the_database
async def test_an_address_only_invited_is_told_to_accept_first(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    email = f"ines-{secrets.token_hex(3)}@gmail.test"
    async with sessions.begin() as session:
        await accounts.invite(session, tenant.org, accounts.Invitee(email, "Ines", Role.admin), held_to_seats=False)
    note = await noted(sessions, email)
    assert note is not None and note.subject.startswith("You have an invitation waiting")


@needs_the_database
async def test_an_address_with_a_password_signs_up_with_it_and_with_no_other(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    email = f"admin@{tenant.slug}.test"
    assert await noted(sessions, email, A_PASSWORD) is None
    note = await noted(sessions, email)
    assert note is not None and note.subject.startswith("You already have an account")
    assert "the password you have" in note.text
