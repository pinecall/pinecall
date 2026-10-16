"""The eval endpoints, one module per noun; `api.py` mounts every router named here."""

from fastapi import APIRouter

from pinecall_runtime.evals.endpoints import calibration, cases, groups, judges, personas, replay, runs, simulations

router = APIRouter()
for each in (calibration, cases, groups, judges, personas, replay, runs, simulations):
    router.include_router(each.router)

__all__ = ["router"]
