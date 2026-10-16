"""Callbacks: somebody the overflow told to wait, and the org's list of them."""

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import keys
from pinecall_runtime.calls.logs import Logs
from pinecall_runtime.calls.repository.heads import HeadRepository
from pinecall_runtime.calls.schemas import CallbackList, CallbackRequest, CallbackRow
from pinecall_runtime.calls.service.serving import NO_SUCH_CALL, is_the_fleet
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.wire.events import CallbackRequested

CALLBACK = "callback.requested"
A_PAGE = 500


# The overflow names the call it answered, and the agent must be that call's org's; an app
# names its own org's agent.
async def request_callback(session: AsyncSession, logs: Logs, actor: Actor, body: CallbackRequest) -> None:
    """Somebody the overflow told to wait for a call back, on the agent's log."""
    keys.check_agent(actor, body.agent)
    owner = await logs.store.owner(body.agent)
    org_wanted = await _org_of_the_call(session, actor, body.call) if is_the_fleet(actor) else actor.org
    if owner is None or owner != org_wanted:
        raise NotFound(f"agent {body.agent} is not this org's")
    wanted = CallbackRequested(channel=body.channel, number=body.number, via="overflow", call=body.call, contact=None)
    await logs.agent(body.agent).append(CALLBACK, wanted.dump())


async def list_callbacks(
    session: AsyncSession, logs: Logs, actor: Actor, *, after: int, agent: str | None
) -> CallbackList:
    """The org's callbacks in the key's env, oldest first, a page at a time."""
    page = await logs.store.across([CALLBACK], after=after, limit=A_PAGE)
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
    return CallbackList(
        requests=[
            CallbackRow.model_validate(
                {"position": our.position, "agent": our.entry.agent, "ts": our.entry.ts, **our.entry.data}
            )
            for our in ours
        ],
        next=page[-1].position if len(page) == A_PAGE else None,
    )


async def _org_of_the_call(session: AsyncSession, actor: Actor, call: str | None) -> str:
    if call is None:
        raise ValidationError("the fleet's key asks a call back for the call it serves: name the call")
    kept = await HeadRepository(session).head_of_call(call)
    if kept is None or kept.scope is None:
        raise NotFound(f"no call {call} was opened: the fleet's key reads and acts for a call once it is")
    if kept.scope.env is not actor.env:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    return kept.scope.org
