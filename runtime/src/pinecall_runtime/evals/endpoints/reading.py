"""What the eval endpoints share: a finished call read by its key, and who asked."""

from collections.abc import Sequence

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.service import declarations
from pinecall_runtime.agents.service.settings import SetByTheClass
from pinecall_runtime.calls import service as calls
from pinecall_runtime.calls.auth import Reader, check_readable
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import Conflict, NotFound
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.postgres import Session
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.parts import JudgesDeclared, PersonasDeclared

NO_SUCH_CALL = "no call {call} in this key's org and env"
STILL_GOING = "call {call} is still going: a case is made of a call that ended"


def asked_by(actor: Actor) -> str:
    """The person behind the key, or the key itself for a server's."""
    return actor.person.id if actor.person is not None else actor.key_id


# The process holding the agent in the scope, else what the scope's last one declared: a judge or a
# persona the class declares is read with nobody holding the agent.
async def declared_in(session: Session, serving: calls.Serving, scope: Scope, slug: str) -> AgentConfig | None:
    """The agent's declaration in the scope, held now or kept from the last process."""
    held = serving.registry.serving(scope, slug, None)
    return await declarations.declared_now_or_last(session, scope, slug, None if held is None else held.config)


async def declared_judges_of(
    session: Session, serving: calls.Serving, scope: Scope, slug: str
) -> JudgesDeclared | None:
    """The judges the agent's class declares in the scope, or None when the org writes them."""
    declared = await declared_in(session, serving, scope, slug)
    return None if declared is None else declared.judges


async def declared_personas_of(
    session: Session, serving: calls.Serving, scope: Scope, slug: str
) -> PersonasDeclared | None:
    """The personas the agent's class declares in the scope, or None when the org writes them."""
    declared = await declared_in(session, serving, scope, slug)
    return None if declared is None else declared.personas


# A door that writes what the class declares answers as the settings doors do: 409, naming the class.
def refuse_if_the_class_owns(declared: object | None, field: str, slug: str) -> None:
    """Refuse a write of the agent's judges or personas while its class declares them."""
    if declared is not None:
        raise SetByTheClass((field,), slug)


async def readable(
    session: Session, serving: calls.Serving, actor: Actor, call: str
) -> tuple[list[Entry], AgentConfig | None]:
    """A call the key reads: its log and its agent's declaration, when held."""
    declared = await check_readable(session, serving, Reader(actor=actor), call)
    entries = await serving.logs.store.whole(call)
    if not entries:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    return entries, declared


async def finished(
    session: Session, serving: calls.Serving, actor: Actor, call: str
) -> tuple[list[Entry], str, Env, int | None]:
    """A call the key reads and that ended: its log, its agent, its env, its settings version."""
    await check_readable(session, serving, Reader(actor=actor), call)
    kept = await calls.head_of_call(session, call)
    entries = await serving.logs.store.whole(call)
    if kept is None or kept.scope is None or not entries:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    keys.check_agent(actor, kept.agent)
    if not is_over(entries):
        raise Conflict(STILL_GOING.format(call=call))
    return list(entries), kept.agent, kept.scope.env, kept.versions.config


def is_over(entries: Sequence[Entry]) -> bool:
    """Whether the call ended."""
    return any(entry.type == "call.ended" for entry in entries)
