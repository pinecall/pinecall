"""Who may call the eval endpoints: an evals key; a words key applies a group's proposed setting."""

from typing import Annotated

from fastapi import Depends, Request

from pinecall_runtime.enums import KeyScope
from pinecall_runtime.evals.service.runs import Runner
from pinecall_runtime.evals.service.simulations import Simulations
from pinecall_runtime.kit.auth import Actor, Authenticator

EvalsKey = Annotated[Actor, Depends(Authenticator(KeyScope.evals))]
WordsKey = Annotated[Actor, Depends(Authenticator(KeyScope.pipeline, KeyScope.words))]


def runner_of(request: Request) -> Runner:
    """The runs this gateway holds agents for."""
    runner: Runner = request.app.state.runner
    return runner


def simulations_of(request: Request) -> Simulations:
    """The simulated calls this gateway is playing."""
    simulations: Simulations = request.app.state.simulations
    return simulations


TheRunner = Annotated[Runner, Depends(runner_of)]
TheSimulations = Annotated[Simulations, Depends(simulations_of)]
