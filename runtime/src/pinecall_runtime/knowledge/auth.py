"""Who may call the knowledge and memory endpoints."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator

KnowledgeKey = Annotated[Actor, Depends(Authenticator(KeyScope.knowledge))]
MemoryKey = Annotated[Actor, Depends(Authenticator(KeyScope.memory))]
