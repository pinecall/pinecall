"""Who may call the billing endpoints: any key for its own limits, the operator for every org's."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.kit.auth import Actor, Authenticator, the_operator

AnyKey = Annotated[Actor, Depends(Authenticator())]
TheOperator = Annotated[Actor, Depends(the_operator)]
