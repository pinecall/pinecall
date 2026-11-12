"""The platform's router: the brand's endpoints, `/metrics`, and the box's pages, which take any path and so go last."""

from fastapi import APIRouter

from runtime.platform.endpoints import brand, metrics, pages

router = APIRouter()
router.include_router(brand.router)
router.include_router(metrics.router)

# Mounted by `api.py` after every other router: its last route matches any path.
pages_router = pages.router
