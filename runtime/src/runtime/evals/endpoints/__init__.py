"""The eval endpoints on one router: runs, simulations, comparisons, a replay, the calibration."""

from fastapi import APIRouter

from runtime.evals.endpoints import calibration, comparisons, replay, runs, simulations

router = APIRouter()
for family in (runs, simulations, comparisons, replay, calibration):
    router.include_router(family.router)
