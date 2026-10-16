"""What a call's log keeps of the values its agent declared private: masked, and sealed aside."""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.text import Json, JsonObject, a_mapping
from pinecall_runtime.wire.base import Entry

logger = logging.getLogger(__name__)

# The key stays, so a reader knows a value exists; the value goes whole, so its type does not leak.
MASK = "***"

# The entries whose data carries the app's state, masked against the state fields declared pii.
CARRY_STATE = frozenset({"state.changed", "call.attached"})

# A tool's arguments, masked against the names its declaration lists under pii.
CARRY_ARGUMENTS = "tool.call"


@dataclass(frozen=True)
class Privacy:
    """What a call's writer masks by: the vault it seals with, the declaration it reads."""

    vault: Vault
    config: AgentConfig


@dataclass(frozen=True)
class Split:
    """An entry's data as the log keeps it, and the values masked in it, by their field."""

    kept: JsonObject
    private: JsonObject


def split(kind: str, data: JsonObject, config: AgentConfig) -> Split:
    """The entry with every value its agent declared private masked, and those values apart."""
    marked = _marked(kind, data, config)
    if marked is None:
        return Split(data, {})
    field, names = marked
    values = data.get(field)
    if not a_mapping(values):
        return Split(data, {})
    private: JsonObject = {name: value for name, value in values.items() if name in names}
    if not private:
        return Split(data, {})
    return Split({**data, field: {**values, **dict.fromkeys(private, MASK)}}, {field: private})


def masked_state(app_state: JsonObject, config: AgentConfig) -> JsonObject:
    """The app's state with every field declared pii masked."""
    return {name: MASK if config.visibility_of(name) == "pii" else value for name, value in app_state.items()}


def restored(entry: Entry, private: JsonObject | None) -> Entry:
    """The entry as its writer wrote it: the private values back where they were masked."""
    if not private:
        return entry
    data = dict(entry.data)
    for field, values in private.items():
        kept = data.get(field)
        if isinstance(kept, dict) and isinstance(values, dict):
            data[field] = {**kept, **values}
    return entry.model_copy(update={"data": data})


def may_be_private(kind: str) -> bool:
    """Whether an entry of this kind can carry a value its agent declared private."""
    return kind == CARRY_ARGUMENTS or kind in CARRY_STATE


def sealed_values(vault: Vault, values: JsonObject) -> str:
    """The private values of one entry, sealed under the vault for the store."""
    return vault.seal(json.dumps(values))


def opened_values(vault: Vault, token: str | None) -> JsonObject | None:
    """The private values a sealed row holds, opened; None for no row, or a key the vault lost."""
    return _opened(vault, token)


def opened_all(vault: Vault, entries: Sequence[Entry], sealed: dict[int, str]) -> list[Entry]:
    """The entries as their writer wrote them, the private values kept aside opened."""
    return [restored(entry, _opened(vault, sealed.get(entry.seq))) for entry in entries]


# A value sealed under a key PINECALL_VAULT_KEY no longer lists stays masked: the call goes on.
def _opened(vault: Vault, token: str | None) -> JsonObject | None:
    if token is None:
        return None
    try:
        values: Json = json.loads(vault.open(token))
    except ServiceUnavailable:
        logger.warning("a private value sealed under a key the vault no longer lists stays masked")
        return None
    return values if isinstance(values, dict) else None


def _marked(kind: str, data: JsonObject, config: AgentConfig) -> tuple[str, frozenset[str]] | None:
    if kind == CARRY_ARGUMENTS:
        spec = config.tools_by_name.get(str(data.get("name")))
        return None if spec is None else ("arguments", spec.pii)
    if kind in CARRY_STATE:
        return "state", frozenset(name for name, seen in config.state_fields.items() if seen == "pii")
    return None
