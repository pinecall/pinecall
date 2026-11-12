"""Insights' dependencies: the key that opens its endpoints, and the agent a window names, the person's to read."""

from typing import Annotated

from fastapi import Depends, Query

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.auth import Authenticator
from runtime.enums import KeyScope

# What the calls counted is read by who reads the calls.
CallsKey = Annotated[Actor, Depends(Authenticator(KeyScope.calls))]


# A person held to some agents reads the windows of those alone.
def the_allowed_filter(actor: CallsKey, agent: Annotated[str | None, Query()] = None) -> str | None:
    """A window's `?agent=`: none is every agent of the scope; one named is the key's person's to read."""
    if agent is not None:
        accounts.check_agent(actor, agent)
    return agent


TheAllowedFilter = Annotated[str | None, Depends(the_allowed_filter)]


def the_allowed_agent(actor: CallsKey, agent: Annotated[str, Query()]) -> str:
    """A drift's `?agent=`: the one agent it compares, the key's person's to read."""
    accounts.check_agent(actor, agent)
    return agent


TheAllowedAgent = Annotated[str, Depends(the_allowed_agent)]
