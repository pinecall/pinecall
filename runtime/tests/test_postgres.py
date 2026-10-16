"""Row-level security as production meets it: a tenant's transaction reads and writes its own org alone."""

from collections.abc import AsyncIterator, Generator
from contextlib import contextmanager

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.models import Org
from pinecall_runtime.platform import service as platform
from pinecall_runtime.postgres import SCOPED_ORG
from pinecall_runtime.providers.models import ProviderKey
from tests.conftest import Tenant, make_tenant, needs_the_database

pytestmark = needs_the_database

# The suite's user owns every table, and an owner is never held by a policy: the gateway connects
# as a role that owns nothing, granted every table's rows by `migrate up`, as production's is.
AS_THE_APP = "pinecall_app_test"
MADE_ONCE = text(
    "DO $$ BEGIN CREATE ROLE pinecall_app_test NOLOGIN; "
    "EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL; END $$"
)


# Two workers granting at once race on the catalog ("tuple concurrently updated"): production
# grants from its one migrate job, the suite's workers one at a time under this lock.
GRANTING = text("select pg_advisory_lock(2654190611)")
GRANTED = text("select pg_advisory_unlock(2654190611)")


@pytest.fixture(scope="session")
async def as_the_app(engine: AsyncEngine) -> AsyncIterator[str]:
    """The app's role, made once and granted every table's rows the way `migrate up` grants them."""
    async with engine.connect() as holder:
        await holder.execute(GRANTING)
        try:
            async with engine.begin() as connection:
                await connection.execute(MADE_ONCE)
            await platform.grant_rows(engine, AS_THE_APP)
        finally:
            await holder.execute(GRANTED)
    yield AS_THE_APP


@contextmanager
def scoped_to(org: str | None) -> Generator[None]:
    """Every transaction begun in the block names this org, as a tenant's request does."""
    token = SCOPED_ORG.set(org)
    try:
        yield
    finally:
        SCOPED_ORG.reset(token)


async def orgs_seen(sessions: async_sessionmaker[AsyncSession], role: str, *orgs: str) -> list[str]:
    """Which of these orgs a transaction acting as the role finds."""
    async with sessions.begin() as session:
        await session.execute(text(f"SET LOCAL ROLE {role}"))
        found = await session.execute(select(Org.id).where(Org.id.in_(orgs)).order_by(Org.id))
        return list(found.scalars())


async def test_a_tenants_transaction_reads_its_own_org_alone(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, as_the_app: str
) -> None:
    """Scoped to one org, the app's role sees that org's row and never the other's."""
    other = await make_tenant(sessions)
    with scoped_to(tenant.org):
        assert await orgs_seen(sessions, as_the_app, tenant.org, other.org) == [tenant.org]
    with scoped_to(other.org):
        assert await orgs_seen(sessions, as_the_app, tenant.org, other.org) == [other.org]


async def test_the_box_reads_every_org_when_it_names_none(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, as_the_app: str
) -> None:
    """The operator's endpoints and the loops name no org: they act as the box, across tenants."""
    other = await make_tenant(sessions)
    with scoped_to(None):
        assert await orgs_seen(sessions, as_the_app, tenant.org, other.org) == sorted([tenant.org, other.org])


async def test_a_tenant_cannot_write_a_row_of_another_org(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant, as_the_app: str
) -> None:
    """The policy checks writes too: a row filed under another org is refused by Postgres itself."""
    other = await make_tenant(sessions)
    with scoped_to(tenant.org), pytest.raises(DBAPIError, match="row-level security"):
        async with sessions.begin() as session:
            await session.execute(text(f"SET LOCAL ROLE {as_the_app}"))
            session.add(ProviderKey(org=other.org, vendor="acme", ciphertext="sealed"))
            await session.flush()
