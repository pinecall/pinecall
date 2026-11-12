"""The knowledge router: bases and their files, a contact's facts, and the three goldens."""

from fastapi import APIRouter

from runtime.knowledge.endpoints import bases, goldens, memory

router = APIRouter()
for family in (bases, memory, goldens):
    router.include_router(family.router)
