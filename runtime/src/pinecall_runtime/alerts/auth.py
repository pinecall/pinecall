"""Who may call the alerts endpoints: evals for the monitors, providers for the webhook."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator

EvalsKey = Annotated[Actor, Depends(Authenticator(KeyScope.evals))]
ProvidersKey = Annotated[Actor, Depends(Authenticator(KeyScope.providers))]
