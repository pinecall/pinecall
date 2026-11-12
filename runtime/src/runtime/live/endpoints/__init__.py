"""The live side's endpoints on one router: one module per client of a live call, each with the key it speaks with."""

from fastapi import APIRouter

from runtime.live.endpoints import apps, chat, desk, dev, line, rooms, visitors, worker

router = APIRouter()
for client in (worker, apps, chat, visitors, desk, dev, line, rooms):
    router.include_router(client.router)
