"""The agents router: the settings and lexicon, the agents and their pipeline, the apps, the line, what they publish."""

from fastapi import APIRouter

from pinecall_runtime.agents.endpoints import agents, apps, judging, published, settings

router = APIRouter()
router.include_router(settings.router)
router.include_router(agents.router)
router.include_router(apps.router)
router.include_router(judging.router)
router.include_router(published.router)
