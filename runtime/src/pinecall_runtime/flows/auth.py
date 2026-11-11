"""Who may call the flows endpoints: the key an app's process serves with, and calls to read its runs."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator

AppKey = Annotated[Actor, Depends(Authenticator(KeyScope.app))]
ReadsRuns = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.calls))]
