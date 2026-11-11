"""Every router of the gateway, mounted on its app in the order a path is matched."""

from fastapi import FastAPI

from runtime.billing import endpoints as billing
from runtime.platform import endpoints as platform


# A domain's router enters here in the commit that builds the domain. The box's pages go last: their
# last route takes any path.
def mount(app: FastAPI) -> None:
    """Mount every domain's router on the app."""
    app.include_router(platform.router)
    app.include_router(billing.router)
    app.include_router(platform.pages_router)
