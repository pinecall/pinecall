"""A scope keeps its last declaration: what the class fixed reads back with no socket, and a scope's is its own."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.service.declarations import declared_in, declared_now_or_last, keep_declaration
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.parts import AgentConfig as Declared
from pinecall_runtime.wire.parts import ModelConfig
from tests.conftest import Tenant, needs_the_database
from tests.fakes.acme import ACME

pytestmark = needs_the_database

SLUG = "front-desk"


@needs_the_database
async def test_what_a_socket_declared_reads_back_once_it_is_gone(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """The first declaration is the class whole, a later one changes what it sends, and the row says what is fixed."""
    scope = Scope(tenant.org, Env.sandbox, "m_ana")
    async with sessions.begin() as session:
        first = Declared(language="es", llm=ModelConfig(provider=ACME, model="acme-1"))
        await keep_declaration(session, scope, SLUG, first, sdk="pinecall/0.11.0", first=True)
        await keep_declaration(session, scope, SLUG, Declared(language=None, record=False), sdk=None, first=False)
    async with sessions.begin() as session:
        read = await declared_in(session, scope, SLUG)
    assert read is not None
    assert (read.fixed, read.language, read.record) == (frozenset({"llm", "record"}), None, False)
    assert read.llm is not None and read.llm.model == "acme-1"


@needs_the_database
async def test_a_new_sockets_first_declaration_replaces_the_row_whole(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A field the process before fixed and the new one leaves out is the settings' again."""
    scope = Scope(tenant.org, Env.sandbox, "m_ana")
    async with sessions.begin() as session:
        await keep_declaration(session, scope, SLUG, Declared(language="es", record=False), sdk=None, first=True)
        await keep_declaration(session, scope, SLUG, Declared(record=False), sdk=None, first=True)
        read = await declared_in(session, scope, SLUG)
    assert read is not None
    assert (read.fixed, read.language) == (frozenset({"record"}), None)


@needs_the_database
async def test_a_scope_reads_its_own_declaration_else_the_orgs_own_never_another_persons(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A developer's sandbox fixes their own scope; a colleague reads the org's own, and nothing of theirs."""
    ana = Scope(tenant.org, Env.sandbox, "m_ana")
    bruno = Scope(tenant.org, Env.sandbox, "m_bruno")
    the_orgs = Scope(tenant.org, Env.sandbox)
    async with sessions.begin() as session:
        await keep_declaration(session, ana, SLUG, Declared(language="es"), sdk=None, first=True)
        assert await declared_in(session, bruno, SLUG) is None
        await keep_declaration(session, the_orgs, SLUG, Declared(record=False), sdk=None, first=True)
        theirs = await declared_in(session, bruno, SLUG)
        mine = await declared_in(session, ana, SLUG)
    assert theirs is not None and theirs.fixed == frozenset({"record"})
    assert mine is not None and mine.fixed == frozenset({"language"})


@needs_the_database
async def test_a_process_holding_the_agent_is_read_before_the_row(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """What is declared now wins over what was declared last; with nothing held, the row answers."""
    scope = Scope(tenant.org, Env.sandbox)
    held = AgentConfig(slug=SLUG, fixed=frozenset({"voice"}))
    async with sessions.begin() as session:
        await keep_declaration(session, scope, SLUG, Declared(language="es"), sdk=None, first=True)
        now = await declared_now_or_last(session, scope, SLUG, held)
        last = await declared_now_or_last(session, scope, SLUG, None)
    assert now is held
    assert last is not None and last.fixed == frozenset({"language"})
