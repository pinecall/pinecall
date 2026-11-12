"""The compliance router: the org's policy and who read its data, its dial guards, consent and the do-not-call list."""

from fastapi import APIRouter

from runtime.compliance.endpoints import consents, policy

router = APIRouter()
for family in (policy, consents):
    router.include_router(family.router)
