"""The platform's router: the brand's endpoints, and the box's pages, which take any path and so go last."""

from fastapi import APIRouter

from runtime.platform.endpoints import brand, pages

router = APIRouter()
router.include_router(brand.router)

# Mounted by `api.py` after every other router: its last route matches any path.
pages_router = pages.router
