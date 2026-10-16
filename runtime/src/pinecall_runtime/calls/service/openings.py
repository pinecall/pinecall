"""What a call is, kept at its open: its context and config, and the turns it carries on."""

import json
from dataclasses import dataclass
from hashlib import sha256

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.calls import private
from pinecall_runtime.calls.context import CallContext
from pinecall_runtime.calls.repository.openings import (
    ConfigRepository,
    OpeningRepository,
    PrivateRepository,
)
from pinecall_runtime.calls.store import Store
from pinecall_runtime.enums import Direction
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import CallDialing, CallRinging
from pinecall_runtime.wire.parts import Route

# What a call that carries another on reads of it: what was said, and what the tools did.
CARRIED = frozenset({"turn.user", "turn.agent", "tool.call", "tool.result"})

# A conversation carried on and on reads its last ten calls; an older one is past what it needs.
CALLS_CARRIED = 10

_CONTEXT: TypeAdapter[CallContext] = TypeAdapter(CallContext)
_CONFIG: TypeAdapter[AgentConfig] = TypeAdapter(AgentConfig)


@dataclass(frozen=True)
class Opening:
    """A call as it opened: what the worker said of it, and the config it runs on."""

    context: CallContext
    config: AgentConfig


async def keep_opening(session: AsyncSession, org: str, context: CallContext, config: AgentConfig) -> None:
    """Keep what the call is: its config once per hash, its opening once."""
    written = _CONFIG.dump_python(config, mode="json")
    hashed = sha256(json.dumps(written, sort_keys=True).encode()).hexdigest()
    await ConfigRepository(session).keep(org, hashed, written)
    await OpeningRepository(session).keep(context.call, org, _CONTEXT.dump_python(context, mode="json"), hashed)


async def opening_of(session: AsyncSession, call: str) -> Opening | None:
    """What the call is, as it was kept when it opened; None for one opened before it was kept."""
    found = await OpeningRepository(session).get(call)
    if found is None:
        return None
    context, config = found
    return Opening(context=_CONTEXT.validate_python(context), config=_CONFIG.validate_python(config))


# Each call keeps only its own turns; the one it continued is named in its opening, and so on back.
async def carried(session: AsyncSession, store: Store, vault: Vault, call: str) -> list[Entry]:
    """The turns of the call and of the calls it continued, oldest first, the private opened."""
    calls: list[str] = []
    at: str | None = call
    while at is not None and len(calls) < CALLS_CARRIED:
        calls.append(at)
        opening = await opening_of(session, at)
        at = None if opening is None else opening.context.continues
    turns: list[Entry] = []
    for earlier in reversed(calls):
        entries, sealed = await store.whole_with_private(earlier)
        whole = private.opened_all(vault, entries, sealed)
        turns += [entry for entry in whole if entry.type in CARRIED]
    return turns


async def opened_whole(session: AsyncSession, store: Store, vault: Vault, call: str) -> list[Entry]:
    """Every entry of the call as its writer wrote it, the private values opened."""
    entries = await store.whole(call)
    return private.opened_all(vault, entries, await PrivateRepository(session).of_log(call))


# The caller is always the far end: on an outbound call that is the `to`.
def arrival_entry(context: CallContext, endpoint: str, *, asked_by: str | None = None) -> tuple[str, JsonObject]:
    """A call's first entry: call.dialing when placed, call.ringing when offered."""
    from_, to = _two_ends(context, endpoint)
    data: JsonObject = {"channel": context.channel.value, "from": from_, "to": to, "run": context.run, "caller": None}
    if context.direction is Direction.outbound:
        # The one record of who placed an outbound call, which is what audits dial spend.
        return "call.dialing", CallDialing.parse({**data, "asked_by": asked_by}, "call.dialing").dump()
    route = Route(channel=context.route.channel, number=context.route.number)
    return "call.ringing", CallRinging.parse({**data, "route": route.dump()}, "call.ringing").dump()


def _two_ends(context: CallContext, endpoint: str) -> tuple[str, str]:
    if context.direction is Direction.outbound:
        return endpoint, context.caller
    return context.caller, endpoint
