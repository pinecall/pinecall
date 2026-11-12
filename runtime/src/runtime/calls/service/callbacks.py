"""Callbacks: somebody the overflow told to wait, and the org's list of them."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.calls.context import log_name
from runtime.calls.log.logs import Logs
from runtime.calls.repository.entries import A_PAGE, EntryRepository
from runtime.calls.repository.heads import HeadRepository
from runtime.calls.service.reading import NEVER_OPENED, NO_SUCH_CALL
from runtime.enums import Channel, KeyScope
from runtime.exceptions import NotFound, ValidationError
from runtime.kit.text import JsonObject
from runtime.scoping import box_wide
from runtime.wire.events import CallbackRequested

CALLBACK = "callback.requested"
NOT_THIS_ORGS = "agent {agent} is not this org's"
NAME_THE_CALL = "the fleet's key asks a call back for the call it serves: name the call"


@dataclass(frozen=True, slots=True)
class CallbackAsked:
    """Somebody the overflow told to wait for a call back: on which agent, where to reach them, from which call."""

    agent: str
    channel: Channel
    number: str
    call: str | None = None


@dataclass(frozen=True, slots=True)
class CallbackPage:
    """A page of the org's callbacks, oldest first, and where the next starts."""

    requests: list[JsonObject]
    next: int | None


# The overflow names the call it answered, and the agent must be that call's org's; an app
# names its own org's agent.
async def request_callback(session: AsyncSession, logs: Logs, actor: Actor, asked: CallbackAsked) -> None:
    """Somebody the overflow told to wait for a call back, on the agent's log."""
    accounts.check_agent(actor, asked.agent)
    with box_wide():
        owner = await HeadRepository(session).owner_of(log_name(None, asked.agent))
    wanted = await _org_of_the_call(session, actor, asked.call) if actor.opens(KeyScope.fleet) else actor.org
    if owner is None or owner != wanted:
        raise NotFound(NOT_THIS_ORGS.format(agent=asked.agent))
    said = CallbackRequested(channel=asked.channel, number=asked.number, via="overflow", call=asked.call, contact=None)
    await logs.agent(asked.agent).append(CALLBACK, said.dump())


async def list_callbacks(session: AsyncSession, actor: Actor, *, after: int, agent: str | None) -> CallbackPage:
    """The org's callbacks in the key's env, oldest first, a page at a time."""
    page = await EntryRepository(session).list_across([CALLBACK], after=after, limit=A_PAGE)
    # An agent's log holds both envs' callbacks: each is the env of the call it names.
    named = [str(item.entry.data["call"]) for item in page if item.entry.data.get("call")]
    envs = await HeadRepository(session).envs_of(named)
    ours = [
        item
        for item in page
        if item.org == actor.org
        and envs.get(str(item.entry.data.get("call"))) is actor.env
        and (agent is None or item.entry.agent == agent)
    ]
    return CallbackPage(
        requests=[
            {"position": our.position, "agent": our.entry.agent, "ts": our.entry.ts, **our.entry.data} for our in ours
        ],
        next=page[-1].position if len(page) == A_PAGE else None,
    )


async def _org_of_the_call(session: AsyncSession, actor: Actor, call: str | None) -> str:
    if call is None:
        raise ValidationError(NAME_THE_CALL)
    kept = await HeadRepository(session).head_of_call(call)
    if kept is None or kept.scope is None:
        raise NotFound(NEVER_OPENED.format(call=call))
    if kept.scope.env is not actor.env:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    return kept.scope.org
