"""The telephony router: the org's carrier accounts, its numbers, its email layout, a worker's, the operator's."""

from fastapi import APIRouter

from runtime.telephony.endpoints import carriers, email, numbers, ops, sms, worker

router = APIRouter()
for family in (carriers, numbers, sms, email, worker, ops):
    router.include_router(family.router)
