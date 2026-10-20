"""Who may call the providers endpoints: the providers scope, the pipeline scope, the operator."""

from typing import Annotated

from fastapi import Depends

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.kit.auth import Actor, Authenticator, the_operator

ProvidersKey = Annotated[Actor, Depends(Authenticator(KeyScope.providers))]
PipelineKey = Annotated[Actor, Depends(Authenticator(KeyScope.pipeline))]
# A note is transcribed on the key a chat runs on (talk) or on one that tunes the pipeline.
EarsKey = Annotated[Actor, Depends(Authenticator(KeyScope.talk, KeyScope.pipeline))]
TheOperator = Annotated[Actor, Depends(the_operator)]
