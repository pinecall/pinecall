"""The settings: which LiveKit a browser joins, on a laptop, behind a name, and on a LiveKit of the operator's own."""

from pinecall_runtime.config import Settings
from pinecall_runtime.enums import Env

REQUIRED = {"PINECALL_VAULT_KEY": "x", "PINECALL_TOKEN_KEY": "y"}


def settings(**named: str) -> Settings:
    return Settings.model_validate({**REQUIRED, **named})


def test_a_laptop_browser_joins_the_livekit_the_runtime_reaches() -> None:
    """No name, no public URL: the one LiveKit, as the gateway reaches it."""
    assert settings(LIVEKIT_URL="ws://127.0.0.1:7880").browser_livekit_url(Env.sandbox) == "ws://127.0.0.1:7880"


def test_a_named_runtime_is_joined_at_its_name() -> None:
    """Behind a name its proxy carries /rtc to LiveKit: both environments join there."""
    named = settings(PINECALL_DOMAIN="voice.example.com")
    assert named.browser_livekit_url(Env.production) == "wss://voice.example.com"
    assert named.browser_livekit_url(Env.sandbox) == "wss://voice.example.com"


def test_the_sandboxs_own_livekit_is_joined_under_the_name() -> None:
    """A cluster's sandbox has its own LiveKit, which the load balancer serves under /sandbox."""
    cluster = settings(
        PINECALL_DOMAIN="cloud.example.com",
        LIVEKIT_PUBLIC_URL="wss://cloud.example.com",
        LIVEKIT_SANDBOX_URL="ws://livekit-sandbox:7880",
    )
    assert cluster.browser_livekit_url(Env.production) == "wss://cloud.example.com"
    assert cluster.browser_livekit_url(Env.sandbox) == "wss://cloud.example.com/sandbox"


def test_a_livekit_of_the_operators_own_is_joined_where_it_is() -> None:
    """With the operator's own LiveKit, the browser goes there, not to the runtime's name."""
    theirs = settings(PINECALL_DOMAIN="voice.example.com", LIVEKIT_PUBLIC_URL="wss://acme.livekit.cloud")
    assert theirs.browser_livekit_url(Env.production) == "wss://acme.livekit.cloud"
    assert theirs.browser_livekit_url(Env.sandbox) == "wss://acme.livekit.cloud"
