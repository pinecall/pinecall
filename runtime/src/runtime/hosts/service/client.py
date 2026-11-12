"""The gateway as an env's runner asks it: its beat, a release's sources, an app's environment."""

from collections.abc import Mapping

import httpx

from runtime.exceptions import UpstreamError
from runtime.kit.text import Json
from runtime.wire.runner import AppEnvironment, RunnerHeartbeatRequest, RunnerHeartbeatResponse, WantedApp

# A release's sources are a few megabytes, read whole.
A_REQUEST_S = 30.0
REFUSED = "{what}: the gateway answered {status}: {text}"


# One method an endpoint, each answer read as its shape of the wire, a refusal said as the failure it
# is: the runner knows no path. Until 2026-11 the three paths and their three checks were written
# inline where each was asked.
class GatewayClient:
    """The gateway as an env's runner asks it, on its runner key and one connection pool."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        """The pool, its key in its headers."""
        self.http = http

    async def beat(self, beat: RunnerHeartbeatRequest) -> RunnerHeartbeatResponse:
        """Say what happened since the last beat; the answer is what should be running."""
        answer = await self._ask("POST", "/v1/runner/heartbeat", "the runner's beat", beat.dump())
        return RunnerHeartbeatResponse.model_validate(answer.json())

    async def get_source(self, app: WantedApp, release: int) -> bytes:
        """A release's sources as they were uploaded, a gzipped tarball."""
        path = f"/v1/runner/apps/{app.org}/{app.name}/releases/{release}/source"
        return (await self._ask("GET", path, "the release's sources")).content

    async def get_environment(self, app: WantedApp) -> Mapping[str, str]:
        """What the app's process is started with: the org's secrets, its key, what the gateway names."""
        path = f"/v1/runner/apps/{app.org}/{app.name}/environment"
        answer = await self._ask("GET", path, "the app's environment")
        return AppEnvironment.model_validate(answer.json()).environment

    async def aclose(self) -> None:
        """Close the connection pool."""
        await self.http.aclose()

    # Away (unreachable, or a 5xx) is what the next beat outlasts; a 4xx is the gateway's answer.
    async def _ask(self, method: str, path: str, what: str, data: Json = None) -> httpx.Response:
        try:
            answer = await self.http.request(method, path, json=data)
        except httpx.HTTPError as unreachable:
            raise UpstreamError(f"{what}: the gateway did not answer: {unreachable}", retryable=True) from unreachable
        if not answer.is_success:
            is_away = answer.status_code >= httpx.codes.INTERNAL_SERVER_ERROR
            said = REFUSED.format(what=what, status=answer.status_code, text=answer.text)
            raise UpstreamError(said, vendor="the gateway", answered=answer.status_code, retryable=is_away)
        return answer


def open_gateway(url: str, key: str) -> GatewayClient:
    """The gateway at this URL, asked with the env's runner key in the header."""
    headers = {"Authorization": f"Bearer {key}"}
    return GatewayClient(httpx.AsyncClient(base_url=url, headers=headers, timeout=A_REQUEST_S))
