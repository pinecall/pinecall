"""The pages the box serves: the widget's files for any site, and the console at every other path."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, Response

from pinecall_runtime.exceptions import NotFound

router = APIRouter(include_in_schema=False)

# The console and the widget the wheel carries (scripts/hatch_build.py puts them here).
BUILT = Path(__file__).resolve().parents[1] / "public"
THE_PAGE = "index.html"
API_PREFIXES = ("v1/", ".well-known/")
NOT_BUILT = "the console is not built into this gateway: `make deploy` builds it in"
NO_SUCH_FILE = "Not Found"
WIDGET_HEADERS = {"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=300"}

# The console is framed by nobody (a page that framed it could dress a click as another), reached
# over HTTPS alone once a browser has seen it, read as the type it is served as, and tells another
# site no more of where it came from than its origin (a sign-in lands with a code in the query).
PAGE_HEADERS = {
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


@router.get("/widget/{file}")
async def widget_file(file: str) -> FileResponse:
    """A file of the widget, for any site to load as a module."""
    root = (BUILT / "widget").resolve()
    found = (root / file).resolve()
    if root not in found.parents or not found.is_file():
        raise NotFound(NO_SUCH_FILE)
    return FileResponse(found, headers=WIDGET_HEADERS)


# The last route `api.py` mounts: a built file is itself, any other path is the page, so a reload
# lands where it was (the page reads its env from the path: `/sandbox/…` is the sandbox's). Never
# cached: a rebuild names new hashed assets in a new index.html.
@router.get("/{path:path}")
async def console_page(path: str) -> Response:
    """The console: an asset of its build, or its page."""
    if path.startswith(API_PREFIXES):
        raise NotFound(NO_SUCH_FILE)
    root = (BUILT / "console").resolve()
    if not (root / THE_PAGE).is_file():
        raise NotFound(NOT_BUILT)
    found = (root / path).resolve()
    if path and root in found.parents and found.is_file() and found.name != THE_PAGE:
        return FileResponse(found, headers=PAGE_HEADERS)
    page = (root / THE_PAGE).read_text(encoding="utf-8")
    return HTMLResponse(page, headers={**PAGE_HEADERS, "cache-control": "no-store"})
