"""The judging router: the org's switch, judges, personas, the dataset's cases and their groups."""

from fastapi import APIRouter

from runtime.judging.endpoints import cases, groups, judges, personas, settings

router = APIRouter()
for family in (settings, judges, personas, cases, groups):
    router.include_router(family.router)
