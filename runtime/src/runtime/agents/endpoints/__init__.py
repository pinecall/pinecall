"""The agents router: an agent's settings, lexicon and canary, what a worker asks of it, its melody, widget, lines."""

from fastapi import APIRouter

from runtime.agents.endpoints import hold_audio, lexicon, published, settings, widget, worker

router = APIRouter()
for family in (settings, lexicon, worker, hold_audio, widget, published):
    router.include_router(family.router)
