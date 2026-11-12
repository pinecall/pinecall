"""The telephony router: the org's carrier accounts and its numbers, what a worker asks, and the operator's."""

from fastapi import APIRouter

from runtime.telephony.endpoints import carriers, numbers, ops, worker

router = APIRouter()
for family in (carriers, numbers, worker, ops):
    router.include_router(family.router)
