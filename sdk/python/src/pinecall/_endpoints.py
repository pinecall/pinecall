"""The gateway's doors this package knocks at, from one base URL, and how a request is signed."""

from urllib.parse import quote, urlsplit, urlunsplit

from pinecall.wire._names import Env

# The world a request acts in. A person's key opens both and this picks one (absent, the
# sandbox); a server token's world is its own, and the header may only agree.
ENV_HEADER = "pinecall-env"


def signed(api_key: str, env: Env | None) -> dict[str, str]:
    """The headers of one request or socket: the key as a Bearer, never in a URL, and the world."""
    headers = {"authorization": f"Bearer {api_key}"} if api_key else {}
    if env is not None:
        headers[ENV_HEADER] = env
    return headers


def apps_url(base: str) -> str:
    """`WS /v1/apps`: the socket an app's agents are held on."""
    return door_at(base, "/v1/apps", websocket=True)


def call_log_url(base: str, call: str) -> str:
    """`GET /v1/calls/{id}/events`: one call's log, as a JSON page or a stream."""
    return door_at(base, f"/v1/calls/{quote(call, safe='')}/events")


def agent_log_url(base: str, agent: str) -> str:
    """`GET /v1/agents/{slug}/calls`: the agent's own log."""
    return door_at(base, f"/v1/agents/{quote(agent, safe='')}/calls")


def lookup_url(base: str, call: str) -> str:
    """`POST /v1/calls/{id}/lookup`: a search the gateway runs for a call this process serves."""
    return door_at(base, f"/v1/calls/{quote(call, safe='')}/lookup")


def door_at(base: str, path: str, *, websocket: bool = False) -> str:
    """The door's URL under the base, its scheme the socket's or the request's."""
    parts = urlsplit(base)
    secure = parts.scheme in ("https", "wss")
    scheme = ("wss" if secure else "ws") if websocket else ("https" if secure else "http")
    return urlunsplit((scheme, parts.netloc, parts.path.rstrip("/") + path, "", ""))
