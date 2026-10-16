"""The agents router: the settings and lexicon, the agents and their pipeline, the apps and the line."""

from fastapi import APIRouter

from pinecall_runtime.agents.endpoints import agents, apps, judging, settings

router = APIRouter()
router.include_router(settings.router)
router.include_router(agents.router)
router.include_router(apps.router)
router.include_router(judging.router)
