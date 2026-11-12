"""Judging's dependencies: the keys that open its endpoints, and a case, a group or an agent loaded and allowed."""

from typing import Annotated

from fastapi import Depends, Path

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.agents.auth import KnownAgent, KnownFilter
from runtime.auth import Authenticator
from runtime.enums import KeyScope
from runtime.judging.models import EvalCase
from runtime.judging.repository.groups import GroupCounted
from runtime.judging.service import cases, groups
from runtime.postgres import Session

# The judges, the personas and the dataset are read and written by who runs the evals; the org's
# switch is read with the calls and set by who answers for what they cost.
EvalsKey = Annotated[Actor, Depends(Authenticator(KeyScope.evals))]
CallsKey = Annotated[Actor, Depends(Authenticator(KeyScope.calls))]
UsageKey = Annotated[Actor, Depends(Authenticator(KeyScope.usage))]


# A person held to some agents reads and writes the cases of those alone.
def the_allowed_agent(slug: KnownAgent, actor: EvalsKey) -> str:
    """The path's agent, the org's own and one the key's person may touch."""
    accounts.check_agent(actor, slug)
    return slug


TheAllowedAgent = Annotated[str, Depends(the_allowed_agent)]


def the_allowed_filter(agent: KnownFilter, actor: EvalsKey) -> str | None:
    """A list's `?agent=`: none is every agent; one named is the org's own and the key's person's to read."""
    if agent is not None:
        accounts.check_agent(actor, agent)
    return agent


TheAllowedFilter = Annotated[str | None, Depends(the_allowed_filter)]


# Another org's case, or nobody's, is the same 404.
async def the_case(case: Annotated[str, Path(alias="id")], actor: EvalsKey, session: Session) -> EvalCase:
    """The path's case, one of the org's, of an agent the key's person may touch."""
    found = await cases.get_case(session, actor.org, case)
    accounts.check_agent(actor, found.agent)
    return found


TheCase = Annotated[EvalCase, Depends(the_case)]


async def the_group(group: Annotated[str, Path(alias="id")], actor: EvalsKey, session: Session) -> GroupCounted:
    """The path's group with its cases counted, one of the org's, of an agent the key's person may touch."""
    found = await groups.get_group(session, actor.org, group)
    accounts.check_agent(actor, found.group.agent)
    return found


TheGroup = Annotated[GroupCounted, Depends(the_group)]
