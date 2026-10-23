"""Who may call the alerts endpoints: evals the monitors, providers the webhook and alerts, the operator all orgs'."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator, the_operator

EvalsKey = Annotated[Actor, Depends(Authenticator(KeyScope.evals))]
ProvidersKey = Annotated[Actor, Depends(Authenticator(KeyScope.providers))]
TheOperator = Annotated[Actor, Depends(the_operator)]
