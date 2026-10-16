"""The call endpoints, one module per family, on one router."""

from fastapi import APIRouter

from pinecall_runtime.calls.endpoints import (
    callbacks,
    chat,
    desk,
    dev,
    entries,
    insights,
    lists,
    metrics,
    readers,
    recordings,
    socket,
    threads,
    usage,
    visitors,
    worker,
)

router = APIRouter()
FAMILIES = (
    worker,
    socket,
    readers,
    visitors,
    desk,
    chat,
    dev,
    entries,
    recordings,
    threads,
    callbacks,
    lists,
    usage,
    insights,
    metrics,
)
for family in FAMILIES:
    router.include_router(family.router)
