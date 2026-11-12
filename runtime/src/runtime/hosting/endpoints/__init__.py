"""The hosting endpoints, one module per noun: apps, releases, usage, secrets, the runner's, and an app's page."""

from fastapi import APIRouter

from runtime.hosting.endpoints import apps, pages, releases, runner, secrets, usage

router = APIRouter()
# `/v1/hosted/usage` before the routes that take an app's name in its place.
for part in (usage, apps, releases, secrets, runner, pages):
    router.include_router(part.router)
