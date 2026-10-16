"""LiveKit's server API, one client per env, on the box's key pair."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

from livekit import api

from pinecall_runtime.config import Settings
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ConfigurationError

NO_LIVEKIT = "LIVEKIT_API_KEY and LIVEKIT_API_SECRET are unset: this process cannot reach the SFU"

type Servers = Mapping[Env, api.LiveKitAPI]


def key_pair(settings: Settings) -> tuple[str, str]:
    """The box's LiveKit key and secret; ConfigurationError when unset."""
    if not settings.livekit_api_key or not settings.livekit_api_secret:
        raise ConfigurationError(NO_LIVEKIT)
    return settings.livekit_api_key, settings.livekit_api_secret.get_secret_value()


# livekit-api opens an HTTP session per client: one per LiveKit and process. Both envs take the
# box's one key pair, so a token the gateway signs opens a room on either.
@asynccontextmanager
async def open_servers(settings: Settings) -> AsyncGenerator[Servers]:
    """Each env's LiveKit client, the one client where the envs share a LiveKit; closed after."""
    key, secret = key_pair(settings)
    production = api.LiveKitAPI(settings.livekit_url_of(Env.production), key, secret)
    servers: dict[Env, api.LiveKitAPI] = {Env.production: production, Env.sandbox: production}
    if settings.livekit_url_of(Env.sandbox) != settings.livekit_url_of(Env.production):
        servers[Env.sandbox] = api.LiveKitAPI(settings.livekit_url_of(Env.sandbox), key, secret)
    try:
        yield servers
    finally:
        for server in dict.fromkeys(servers.values()):
            await server.aclose()
