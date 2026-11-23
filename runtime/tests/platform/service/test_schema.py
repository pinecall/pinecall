"""The roles setup gives a server's database: one that signs in and owns nothing, and a password changed."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from runtime.platform.service import schema
from tests.conftest import needs_the_database

A_LOGIN = "pinecall_login_test"
WHAT_IT_IS = text("select rolcanlogin, rolsuper, rolcreaterole, rolcreatedb from pg_roles where rolname = :role")


@needs_the_database
async def test_a_login_role_signs_in_and_may_change_no_table(engine: AsyncEngine) -> None:
    """Made, then kept with another password (a quote in it too); it may not make a table by itself."""
    await schema.make_login(engine, A_LOGIN, "a-first-password")
    await schema.make_login(engine, A_LOGIN, "it's another one")
    await schema.set_password(engine, A_LOGIN, "and a third")
    async with engine.connect() as connection:
        found = (await connection.execute(WHAT_IT_IS, {"role": A_LOGIN})).one()
    assert tuple(found) == (True, False, False, False)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with engine.begin() as connection:
            await connection.execute(text(f"set local role {A_LOGIN}"))
            await connection.execute(text("create table pinecall_login_test_made (id int)"))
