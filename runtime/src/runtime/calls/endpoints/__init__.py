"""The record's endpoints on one router: one module per resource of the record."""

from fastapi import APIRouter

from runtime.calls.endpoints import callbacks, inbox, lists, logs, recordings, traceback, usage

router = APIRouter()
for resource in (logs, lists, inbox, recordings, usage, callbacks, traceback):
    router.include_router(resource.router)
