"""The agents router: an agent's settings, lexicon, canary, pipeline, melody, widget and lines; what a worker asks."""

from fastapi import APIRouter

from runtime.agents.endpoints import hold_audio, lexicon, pipeline, published, settings, widget, worker

router = APIRouter()
for family in (settings, lexicon, worker, pipeline, hold_audio, widget, published):
    router.include_router(family.router)
