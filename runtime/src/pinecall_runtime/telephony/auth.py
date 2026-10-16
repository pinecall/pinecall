"""Who may call the telephony endpoints: numbers, talk, calls, the worker, the operator."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator, the_operator

NumbersKey = Annotated[Actor, Depends(Authenticator(KeyScope.numbers))]
TalkKey = Annotated[Actor, Depends(Authenticator(KeyScope.talk))]
CallsKey = Annotated[Actor, Depends(Authenticator(KeyScope.calls))]
# A worker asks with its fleet's key; a tenant's own worker with an app key.
WorkerKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.fleet))]
TheOperator = Annotated[Actor, Depends(the_operator)]
