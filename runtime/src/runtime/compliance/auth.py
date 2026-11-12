"""Compliance's dependencies: the keys that open the policy and the reads, and the consents of a number."""

from typing import Annotated

from fastapi import Depends

from runtime.actor import Actor
from runtime.auth import Authenticator
from runtime.enums import KeyScope

# The policy and the trail of reads are the team's.
TeamKey = Annotated[Actor, Depends(Authenticator(KeyScope.team))]
# A fact about a number is written by who may place a call, and read by who may read one.
TalkKey = Annotated[Actor, Depends(Authenticator(KeyScope.talk))]
CallsKey = Annotated[Actor, Depends(Authenticator(KeyScope.calls))]
