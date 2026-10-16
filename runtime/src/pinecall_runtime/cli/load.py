"""`load`: synthetic calls held against a gateway's sandbox exactly as workers hold them, and measured."""

from pathlib import Path
from typing import Annotated

import typer

from pinecall_runtime.cli.command import OK, context_of, verb
from pinecall_runtime.exceptions import ConfigurationError
from pinecall_runtime.jobs import service as jobs

NO_KEY = "PINECALL_WORKER_KEY is unset: the load opens its calls with the sandbox fleet's key"


@verb
async def load(
    ctx: typer.Context,
    org: Annotated[str, typer.Option("--org", help="The org the calls are opened for.")],
    agent: Annotated[str, typer.Option("--agent", help="The agent the calls are opened for.")],
    script: Annotated[Path, typer.Option("--script", help="A call's log as JSON, replayed per call.")],
    calls: Annotated[int, typer.Option("--calls", help="How many at once at the top.")],
    ramp: Annotated[float, typer.Option("--ramp", help="Seconds to reach them, linearly.")],
    minutes: Annotated[float, typer.Option("--minutes", help="How long the top is held.")],
) -> int:
    """Hold the calls against the gateway, then print what was measured."""
    context = context_of(ctx)
    key = context.settings.worker_key
    if key is None:
        raise ConfigurationError(NO_KEY)
    plan = jobs.Plan(
        org=org, agent=agent, script=jobs.read_script(script), calls=calls, ramp_s=ramp, hold_s=minutes * 60
    )
    tally = await jobs.measure_load(context.settings.gateway_url, key.get_secret_value(), plan)
    if context.out.as_json:
        context.out.data(tally)
    else:
        context.out.lines(jobs.report_of(tally, plan.hold_s))
    return OK
