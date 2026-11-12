"""The time apps served: an org's own, and every org's for the operator."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.auth import TheOperator
from runtime.hosting import schemas
from runtime.hosting.service import usage
from runtime.live.auth import AppKey
from runtime.postgres import Session, TheBoxSession

router = APIRouter()


@router.get("/v1/hosted/usage")
async def read_usage(
    actor: AppKey, session: Session, month: Annotated[str | None, Query()] = None
) -> schemas.ServedPage:
    """The time the org's apps served here per UTC day, in one month: this one by default."""
    return schemas.ServedPage.of_usage(await usage.usage_of_month(session, month, org=actor.org, env=actor.env))


@router.get("/v1/ops/hosted-usage")
async def read_box_usage(
    _actor: TheOperator, session: TheBoxSession, month: Annotated[str | None, Query()] = None
) -> schemas.ServedPage:
    """The time every org's apps served, both envs, per UTC day, one month: what bills them."""
    return schemas.ServedPage.of_usage(await usage.usage_of_month(session, month))
