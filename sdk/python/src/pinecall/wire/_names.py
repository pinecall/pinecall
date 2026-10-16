"""The runtime's words the wire is written in: JSON, the worlds, the channels, a quota."""

from typing import TYPE_CHECKING, Literal, TypeAlias, Union

from typing_extensions import TypeAliasType

# A recursive alias: pyright reads it as written for type checking, pydantic as a TypeAliasType
# whose self-references are strings, since `|` cannot join a string at runtime.
if TYPE_CHECKING:
    Json: TypeAlias = "str | int | float | bool | list[Json] | dict[str, Json] | None"
else:
    Json = TypeAliasType(
        "Json",
        Union[str, int, float, bool, list["Json"], dict[str, "Json"], None],  # noqa: UP007
    )

JsonObject: TypeAlias = dict[str, Json]

# A key belongs to one world; its agents, numbers and calls are isolated to it.
Env: TypeAlias = Literal["production", "sandbox"]

# phone: SIP into a LiveKit room; web: the widget over WebRTC; whatsapp: text.
Channel: TypeAlias = Literal["phone", "web", "whatsapp"]

# How the call is had: spoken (a room, a voice) or written (a text session); `web` is either.
Medium: TypeAlias = Literal["voice", "text"]

Direction: TypeAlias = Literal["inbound", "outbound"]

# app: the tenant's backend. participant: the caller's browser.
EventSource: TypeAlias = Literal["app", "participant"]

QuotaName: TypeAlias = Literal[
    "minutes",
    "messages",
    "agents",
    "concurrent_calls",
    "memory_facts",
    "knowledge_chunks",
    "numbers",
    "seats",
    "llm_tokens",
    "hosted_apps",
    "evals",
    "simulations",
    "budget_usd",
]
