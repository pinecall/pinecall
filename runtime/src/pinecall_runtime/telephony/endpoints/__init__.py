"""The telephony router: the org's accounts and numbers, dialling out, consent, the operator's."""

from fastapi import APIRouter

from pinecall_runtime.telephony.endpoints import consents, numbers, ops

router = APIRouter()
router.include_router(numbers.router)
router.include_router(consents.router)
router.include_router(ops.router)
