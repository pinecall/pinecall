"""A sign-up founds an org: its admin seated with their address proven, a key, and the console's code."""

import os
import secrets

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts.service import orgs, people
from runtime.accounts.service.key_cache import KeyCache
from runtime.enums import MemberStatus
from runtime.kit.crypto import Vault
from runtime.signin.service import signup
from runtime.signin.service.codes import LoginCodes
from tests.conftest import needs_the_database


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
