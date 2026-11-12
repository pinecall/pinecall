"""`GET /metrics`: what the gateway counted and holds, as Prometheus text, to the addresses it trusts alone."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from runtime.handles import TheSettings
from runtime.platform.auth import TheCollectors
from runtime.platform.service import metrics

router = APIRouter()

# The load balancer sets it on every request it passes on: a request that carries it came from off the box.
FORWARDED = "x-forwarded-for"


@router.get("/metrics", include_in_schema=False)
async def read_metrics(request: Request, settings: TheSettings, collectors: TheCollectors) -> PlainTextResponse:
    """What each owner of the gateway counted since it started and holds now, in Prometheus's text."""
    client = "" if request.client is None else request.client.host
    metrics.check_reader(client, FORWARDED in request.headers, settings.metrics_from)
    text = await metrics.read_metrics(collectors, time.time())
    return PlainTextResponse(text, media_type=metrics.TEXT_FORMAT)
