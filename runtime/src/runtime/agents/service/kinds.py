"""What an agent is — a class an app holds, or a Studio definition the gateway holds — by its SDK word and its key."""

from typing import Literal

# The SDK word the gateway's own holder registers a Studio agent under: what tells one from a class.
BUILT_IN_STUDIO = "studio"
# What the id of the key the gateway's own holder registers with starts with: no app's key does.
STUDIO_KEYS = "studio:"

type AgentKind = Literal["class", "studio"]


def kind_of(sdk: str | None) -> AgentKind:
    """The kind of an agent registered under this SDK word."""
    return "studio" if sdk == BUILT_IN_STUDIO else "class"


def is_studio_key(key_id: str) -> bool:
    """Whether the key is the one the gateway's own Studio holder registers with."""
    return key_id.startswith(STUDIO_KEYS)
