"""Evals' dependencies: the key that runs them, and the harness the lifespan built."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from runtime.evals.parts import Harness
from runtime.judging.auth import EvalsKey

# A run, a simulation, a comparison, a replay and a label are asked by who runs the evals: the key
# judging's endpoints take (`judging.auth.EvalsKey`), named here for evals' own endpoints.
__all__ = ["EvalsKey", "TheHarness", "harness_of"]


def harness_of(connection: HTTPConnection) -> Harness:
    """What places and plays a test call on this gateway, one of each."""
    harness: Harness = connection.state.harness
    return harness


TheHarness = Annotated[Harness, Depends(harness_of)]
