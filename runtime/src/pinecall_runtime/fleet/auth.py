"""Who may call the fleet endpoints: a fleet's key for a worker or KEDA, the operator for the rest."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator, the_operator

# An env's fleet key: the workers beat with it, and KEDA asks the demand with it.
FleetKey = Annotated[Actor, Depends(Authenticator(KeyScope.fleet))]
TheOperator = Annotated[Actor, Depends(the_operator)]
