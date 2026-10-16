"""Who may erase and export: the team for its own org's data, the operator for an org or an agent whole."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator, the_operator

TeamKey = Annotated[Actor, Depends(Authenticator(KeyScope.team))]
TheOperator = Annotated[Actor, Depends(the_operator)]
