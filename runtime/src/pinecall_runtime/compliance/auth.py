"""Who may call the compliance endpoints: the team for the policy and reads, providers for telemetry."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator

TeamKey = Annotated[Actor, Depends(Authenticator(KeyScope.team))]
ProvidersKey = Annotated[Actor, Depends(Authenticator(KeyScope.providers))]
