"""What an agent is — a class an app holds, or a Studio definition the gateway holds — by its SDK word."""

from typing import Literal

# The SDK word the gateway's own holder registers a Studio agent under: what tells one from a class.
BUILT_IN_STUDIO = "studio"

AgentKind = Literal["class", "studio"]


def kind_of(sdk: str | None) -> AgentKind:
    """The kind of an agent registered under this SDK word."""
    return "studio" if sdk == BUILT_IN_STUDIO else "class"
