"""The last declaration each scope's app made of an agent, kept past the socket: what the class fixes."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.repository import DeclarationRepository
from pinecall_runtime.agents.service.declared import with_app_fields
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.wire.parts import AgentConfig as Declaration


# A socket's first declaration is the class whole and replaces the row; a later one changes the
# fields it sends, as the config in the registry changes, so the row reads as that config does.
async def keep_declaration(
    session: AsyncSession, scope: Scope, slug: str, declaration: Declaration, *, sdk: str | None, first: bool
) -> dict[str, Any]:
    """Keep what the app declared of the agent as the scope's, merged into what it declared before; the row's body."""
    declarations = DeclarationRepository(session)
    sent = declaration.dump()
    before = None if first else await declarations.get(scope, slug)
    merged = sent if before is None or before.holder != scope.holder else {**before.declared, **sent}
    await declarations.put(scope, slug, merged, sdk)
    return merged


async def declared_in(session: AsyncSession, scope: Scope, slug: str) -> AgentConfig | None:
    """The agent as the scope's last app declared it (the org's own when the scope never did), or None."""
    row = await DeclarationRepository(session).get(scope, slug)
    if row is None:
        return None
    return with_app_fields(AgentConfig(slug=slug), Declaration.model_validate(row.declared), first=True)


async def declared_now_or_last(
    session: AsyncSession, scope: Scope, slug: str, held: AgentConfig | None
) -> AgentConfig | None:
    """What a process holding the agent declares, else what the scope's last one did."""
    return held if held is not None else await declared_in(session, scope, slug)
