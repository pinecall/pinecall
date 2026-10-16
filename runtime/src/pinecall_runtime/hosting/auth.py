"""Who may call the hosting endpoints: an app key for an org's apps and secrets, the env's runner."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator, the_operator

AppKey = Annotated[Actor, Depends(Authenticator(KeyScope.app))]
RunnerKey = Annotated[Actor, Depends(Authenticator(KeyScope.runner))]
TheOperator = Annotated[Actor, Depends(the_operator)]
