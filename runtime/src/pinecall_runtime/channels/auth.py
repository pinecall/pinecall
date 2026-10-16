"""Who may call the channels endpoints: the operator for every route, a worker for its call's."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator, the_operator

TheOperator = Annotated[Actor, Depends(the_operator)]
# A worker asks with its fleet's key; a tenant's own worker with an app key.
WorkerKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.fleet))]
