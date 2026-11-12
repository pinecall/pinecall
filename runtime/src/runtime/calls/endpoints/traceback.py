"""The operator's traceback: what the box keeps of one number, for a carrier that asks."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.auth import TheOperator
from runtime.calls import schemas
from runtime.calls.service import traceback
from runtime.postgres import TheBoxSession

router = APIRouter()


@router.get("/v1/ops/traceback")
async def trace_number(
    actor: TheOperator,
    session: TheBoxSession,
    number: Annotated[str, Query()],
    since: Annotated[float | None, Query()] = None,
) -> schemas.Traceback:
    """What the box keeps of one number since a day: every phone call with it and every dial to it."""
    return schemas.Traceback.of(await traceback.trace_number(session, number, since, read_by=actor.name))
