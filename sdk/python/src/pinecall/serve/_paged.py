"""The app's page on this machine: its folder, and the routes the platform answers when deployed."""

import json
import mimetypes
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from typing_extensions import override

from pinecall._endpoints import door_at, signed
from pinecall.wire._names import Env

PAGE_PORT = 4747
"""The port the page is served on unless `PINECALL_PAGE_PORT` names another."""

INDEX = "index.html"
NOT_BUILT = "the page is not built yet: build it into the folder app.page names, and reload"


@dataclass(frozen=True)
class Paging:
    """What a page is served with: its folder, the agent a visitor reaches, the door, a port."""

    folder: Path
    agent: str
    url: str
    api_key: str
    env: Env | None
    port: int


@dataclass(frozen=True)
class Said:
    """One answer: its status, its body and what the body is."""

    status: int
    body: bytes
    kind: str = "application/json"


def serve_page(paging: Paging) -> ThreadingHTTPServer:
    """Serve the page on a thread of its own until `shutdown()`; OSError when the port is taken."""

    class Page(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._said(got(paging, urlsplit(self.path).path))

        def do_POST(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            self._said(posted(paging, urlsplit(self.path).path, self.rfile.read(length)))

        @override
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _said(self, said: Said) -> None:
            self.send_response(said.status)
            self.send_header("content-type", said.kind)
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(said.body)))
            self.end_headers()
            self.wfile.write(said.body)

    server = ThreadingHTTPServer(("127.0.0.1", paging.port), Page)
    threading.Thread(target=server.serve_forever, name="pinecall-page", daemon=True).start()
    return server


def got(paging: Paging, path: str) -> Said:
    """A GET: the page's config, or a file of the built folder."""
    if path == "/pinecall/config":
        # No captcha here: the key is the developer's own, and nobody else reaches the port.
        return Said(200, json.dumps({"agent": paging.agent, "turnstile": None}).encode())
    return file_of(paging.folder, path)


def posted(paging: Paging, path: str, body: bytes) -> Said:
    """A POST: a visitor's ticket or code, asked of the gateway with the key."""
    if path == "/pinecall/token":
        asked = _read(body)
        wanted: dict[str, object] = {
            "agent": paging.agent,
            "scope": "chat" if asked.get("scope") == "chat" else "talk",
        }
        resume = asked.get("resume")
        if isinstance(resume, str):
            wanted["resume"] = resume
        return passed(paging, "/v1/tokens", wanted)
    if path == "/pinecall/code":
        return passed(paging, "/v1/codes", {"agent": paging.agent})
    return Said(405, b'{"detail": "a page is read"}')


def passed(paging: Paging, door: str, body: dict[str, object]) -> Said:
    """What the gateway answered, passed on to the page as it is."""
    headers = signed(paging.api_key, paging.env)
    try:
        answered = httpx.post(door_at(paging.url, door), json=body, headers=headers, timeout=30.0)
    except httpx.HTTPError as failed:
        return Said(502, json.dumps({"detail": str(failed)}).encode())
    return Said(answered.status_code, answered.content)


# A path that names no file is the page itself, so its own router reads it.
def file_of(folder: Path, path: str) -> Said:
    """The file a path names inside the folder, or the page's index for a path with no extension."""
    root = folder.resolve()
    asked = (root / unquote(path).lstrip("/")).resolve()
    inside = asked == root or root in asked.parents
    found = asked if inside and asked.is_file() else root / INDEX
    if not inside or (found != asked and Path(path).suffix) or not found.is_file():
        gone = f"the page has no file {path}" if (root / INDEX).is_file() else NOT_BUILT
        return Said(404, json.dumps({"detail": gone}).encode())
    kind = mimetypes.guess_type(found.name)[0] or "application/octet-stream"
    return Said(200, found.read_bytes(), kind)


def _read(body: bytes) -> dict[str, object]:
    try:
        read: object = json.loads(body or b"{}")
    except ValueError:
        return {}
    return read if isinstance(read, dict) else {}  # pyright: ignore[reportUnknownVariableType]
