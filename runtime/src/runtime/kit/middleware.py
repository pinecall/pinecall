"""ASGI middleware with no business noun: CORS by origins read per request, a ceiling on bodies, names to a prefix."""

import re
from collections.abc import Callable

from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
PREFLIGHT_KEPT_S = 600
READ_HEADERS = ("authorization", "last-event-id", "accept", "range")
READ_EXPOSED = ("content-range", "accept-ranges", "content-length")
TOO_LARGE = "the body is over {most} MiB, more than any endpoint takes"

type Origins = Callable[[Scope], tuple[str, ...]]
type Domain = Callable[[Scope], str | None]


# Read per request: the settings are loaded by the lifespan, after the middleware is built.
class AllowedOrigins:
    """CORS under a prefix for the origins allowed; any page GETs what `any_page` matches, POSTs `any_page_says`."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        prefix: str,
        origins: Origins,
        headers: tuple[str, ...],
        any_page: re.Pattern[str],
        any_page_says: re.Pattern[str],
    ) -> None:
        """Nothing allowed until `origins` says what."""
        self.app = app
        self.prefix = prefix
        self.origins = origins
        self.headers = headers
        self.any_page = any_page
        self.any_page_says = any_page_says
        self.cors: tuple[tuple[str, ...], CORSMiddleware] | None = None
        self.reads = CORSMiddleware(
            app,
            allow_origins=("*",),
            allow_methods=("GET",),
            allow_headers=READ_HEADERS,
            expose_headers=READ_EXPOSED,
            max_age=PREFLIGHT_KEPT_S,
        )
        # A token in the URL and an empty body: no header a browser asks leave for, no credentials.
        self.says = CORSMiddleware(app, allow_origins=("*",), allow_methods=("POST",), max_age=PREFLIGHT_KEPT_S)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Route an allowed origin's request through CORS, and anything else straight in."""
        path = str(scope.get("path", ""))
        if scope["type"] != "http" or not path.startswith(self.prefix):
            await self.app(scope, receive, send)
            return
        origin = Headers(scope=scope).get("origin")
        allowed = self.origins(scope) if origin else ()
        if origin and origin not in allowed and self.any_page.match(path):
            await self.reads(scope, receive, send)
            return
        if origin and origin not in allowed and self.any_page_says.match(path):
            await self.says(scope, receive, send)
            return
        if not origin or origin not in allowed:
            await self.app(scope, receive, send)
            return
        await self._cors_for(allowed)(scope, receive, send)

    def _cors_for(self, allowed: tuple[str, ...]) -> CORSMiddleware:
        if self.cors is None or self.cors[0] != allowed:
            cors = CORSMiddleware(
                self.app,
                allow_origins=allowed,
                allow_methods=METHODS,
                allow_headers=self.headers,
                max_age=PREFLIGHT_KEPT_S,
            )
            self.cors = (allowed, cors)
        return self.cors[1]


# Said by Content-Length, refused at once; said by nothing (chunked), counted as it comes and
# answered 413 the chunk it passes the most. The endpoint is then told the client left, so it
# stops reading, and whatever it answers after is dropped: the 413 is the one answer.
class BodyCeiling:
    """No request's body is over `most` bytes."""

    def __init__(self, app: ASGIApp, *, most: int) -> None:
        """The app it stands in front of."""
        self.app = app
        self.most = most

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass the request on, its body counted."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        too_large = JSONResponse({"detail": TOO_LARGE.format(most=self.most // (1024 * 1024))}, status_code=413)
        announced = Headers(scope=scope).get("content-length")
        if announced is not None and announced.isdigit() and int(announced) > self.most:
            await too_large(scope, receive, send)
            return
        counted = 0
        answered = False

        async def counting() -> Message:
            nonlocal counted, answered
            message = await receive()
            counted += len(message.get("body", b""))
            if counted > self.most and not answered:
                answered = True
                await too_large(scope, receive, send)
            return {"type": "http.disconnect"} if answered else message

        async def unless_answered(message: Message) -> None:
            if not answered:
                await send(message)

        await self.app(scope, counting, unless_answered)


# The routes under the prefix answer by the name in their path, so they are ordinary routes; this is
# what puts the name a request came in by into its path.
class NamesUnder:
    """A request by a name under `domain` goes to `prefix`/<name>: `own` paths as they are, the rest as files."""

    def __init__(self, app: ASGIApp, *, domain: Domain, prefix: str, own: str, files: str) -> None:
        """The app it stands in front of."""
        self.app = app
        self.domain = domain
        self.prefix = prefix
        self.own = own
        self.files = files

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass the request on, its path naming the host it came in by when that is one under the domain."""
        domain = self.domain(scope) if scope["type"] == "http" else None
        host = Headers(scope=scope).get("host", "").split(":")[0].lower() if domain else ""
        if not domain or not host.endswith(f".{domain.lower()}"):
            await self.app(scope, receive, send)
            return
        asked: str = scope["path"]
        path = f"{self.prefix}/{host}{asked if asked.startswith(self.own) else self.files + asked}"
        await self.app({**scope, "path": path, "raw_path": path.encode()}, receive, send)
