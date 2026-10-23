"""The access log as the key reads it: its own environment's rows, never the other's."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import Env, ReadKind
from pinecall_runtime.kit.auth import Scope
from tests.conftest import Gateway, Tenant, needs_the_services

pytestmark = needs_the_services

PRODUCTION = {"pinecall-env": "production"}


async def read_in(sessions: async_sessionmaker[AsyncSession], tenant: Tenant, env: Env, call: str) -> None:
    """The tenant's admin read the call's log in the env, as the endpoints write it down."""
    async with sessions.begin() as session:
        await compliance.record_read(session, Scope(tenant.org, env), call, ReadKind.log, by=tenant.member)


async def subjects(gateway: Gateway, headers: dict[str, str], **query: str) -> list[tuple[str, str | None]]:
    """What the key's trail of reads names, newest first, with the env each row carries."""
    answered = await gateway.http.get("/v1/org/reads", params=query, headers=headers)
    assert answered.status_code == 200, answered.text
    return [(row["subject"], row["env"]) for row in answered.json()["reads"]]


async def test_a_key_reads_its_own_environments_trail_and_never_the_others(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Two reads, one in each env: the sandbox's key sees one, production's the other, `--prod` is not both."""
    await read_in(sessions, tenant, Env.sandbox, "call_in_the_sandbox")
    await read_in(sessions, tenant, Env.production, "call_in_production")
    assert await subjects(gateway, tenant.person) == [("call_in_the_sandbox", "sandbox")]
    assert await subjects(gateway, {**tenant.person, **PRODUCTION}) == [("call_in_production", "production")]


async def test_a_subject_narrows_the_trail_inside_the_environment_alone(
    gateway: Gateway, tenant: Tenant, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The same call read in both envs: each key finds its own env's row for it, and one row."""
    await read_in(sessions, tenant, Env.sandbox, "call_in_both")
    await read_in(sessions, tenant, Env.production, "call_in_both")
    assert await subjects(gateway, tenant.person, subject="call_in_both") == [("call_in_both", "sandbox")]
    assert await subjects(gateway, {**tenant.person, **PRODUCTION}, subject="call_in_both") == [
        ("call_in_both", "production")
    ]
