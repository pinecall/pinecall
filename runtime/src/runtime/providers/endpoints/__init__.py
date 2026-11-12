"""The providers router: what an org can run, its keys and the box's, voices, transcriptions, the row, telemetry."""

from fastapi import APIRouter

from runtime.providers.endpoints import keys, ops, telemetry, transcriptions, vendors, voices

router = APIRouter()
for family in (vendors, keys, voices, transcriptions, ops, telemetry):
    router.include_router(family.router)
