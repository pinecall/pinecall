"""Who may call the hosting endpoints: an app key for an org's apps and secrets, the env's runner; the pages' domain."""

from typing import Annotated

from fastapi import Depends
from starlette.types import Scope

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator, the_operator
from pinecall_runtime.kit.handles import Handles

AppKey = Annotated[Actor, Depends(Authenticator(KeyScope.app))]
RunnerKey = Annotated[Actor, Depends(Authenticator(KeyScope.runner))]
TheOperator = Annotated[Actor, Depends(the_operator)]


# Read per request: the settings are loaded by the lifespan, after the middleware is built.
def pages_domain(scope: Scope) -> str | None:
    """The domain apps' pages are served under, or None on a box that serves none."""
    handles: object = getattr(scope["app"].state, "handles", None)
    return handles.settings.pages_domain if isinstance(handles, Handles) else None
