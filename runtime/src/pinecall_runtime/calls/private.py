"""What a call's log keeps of the values its agent declared private: masked, and sealed aside."""

import json
import logging
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import cast

from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.text import Json, JsonObject, a_mapping
from pinecall_runtime.wire.base import Entry

logger = logging.getLogger(__name__)

# The key stays, so a reader knows a value exists; the value goes whole, so its type does not leak.
MASK = "***"

# A value shorter than this is never learned as a secret: "7", "ok" or "Al" cannot be told from a
# word, and masking it would mask every such digit or word the agent writes after it. The argument
# is still masked by its name; only its value is not hunted in what else was written.
LEAST_SECRET_CHARS = 3

# What the agent wrote down, by entry: the fields of its data a private value may be in. A tool's
# arguments and what it answered, the state it holds, and the lines it logged itself. What was said
# (turn.user, turn.agent) is the caller's and the model's words, never masked.
WRITTEN_DOWN: dict[str, tuple[str, ...]] = {
    "tool.call": ("arguments",),
    "tool.result": ("output", "error", "summary"),
    "state.changed": ("state",),
    "call.attached": ("state",),
    "custom": ("data",),
}

# The entries whose state is masked field by field against the fields declared pii.
CARRY_STATE = frozenset({"state.changed", "call.attached"})

# A tool's arguments, masked against the names its declaration lists under pii, and where the
# values of those arguments are learned.
CARRY_ARGUMENTS = "tool.call"


@dataclass
class Privacy:
    """What a call's writer masks by: the vault it seals with, the declaration it reads, and the values.

    `values` are the private values the call's tool calls carried, learned as they are written or
    forwarded: every later entry the agent wrote is masked of them, wherever they appear.
    """

    vault: Vault
    config: AgentConfig
    values: set[str] = field(default_factory=set[str])
    # The newest tool.call whose values were asked of the store, so a gateway asks for what is new.
    through: int = 0

    @property
    def active(self) -> bool:
        """Whether the declaration names anything private at all: when not, nothing is masked or sealed."""
        pii_fields = any(seen == "pii" for seen in self.config.state_fields.values())
        return pii_fields or any(spec.pii for spec in self.config.tools)

    def learn(self, kind: str, data: JsonObject) -> None:
        """Take the values of the arguments a tool.call lists under pii as private from here on."""
        if kind != CARRY_ARGUMENTS:
            return
        spec = self.config.tools_by_name.get(str(data.get("name")))
        arguments = data.get("arguments")
        if spec is None or not a_mapping(arguments):
            return
        for name in spec.pii:
            self.values.update(
                leaf for leaf in _leaves(cast("Json", arguments.get(name))) if len(leaf) >= LEAST_SECRET_CHARS
            )

    def secrets(self) -> list[str]:
        """The private values, the longest first, so one that holds another is masked whole."""
        return sorted(self.values, key=len, reverse=True)


@dataclass(frozen=True)
class Split:
    """An entry's data as the log keeps it, and the values masked in it, by their field."""

    kept: JsonObject
    private: JsonObject


def split(kind: str, data: JsonObject, config: AgentConfig, secrets: Sequence[str] = ()) -> Split:
    """The entry with every value its agent declared private masked, and those values apart.

    A tool's arguments and a state field are private by name; whatever else the agent wrote down
    is masked of `secrets` wherever one stands as a whole word, in a string or as a whole leaf.
    """
    fields = WRITTEN_DOWN.get(kind)
    if fields is None:
        return Split(data, {})
    found = _Secrets.of(secrets)
    declared = _declared(kind, data, config)
    kept = dict(data)
    private: JsonObject = {}
    for name in fields:
        if name not in data:
            continue
        by_name = declared[1] if declared is not None and declared[0] == name else frozenset[str]()
        masked, aside = _masked(data[name], by_name, found)
        if aside is not None:
            kept[name] = masked
            private[name] = aside
    return Split(kept, private) if private else Split(data, {})


def masked_state(app_state: JsonObject, config: AgentConfig) -> JsonObject:
    """The app's state with every field declared pii masked."""
    return {name: MASK if config.visibility_of(name) == "pii" else value for name, value in app_state.items()}


def restored(entry: Entry, private: JsonObject | None) -> Entry:
    """The entry as its writer wrote it: the private values back where they were masked."""
    if not private:
        return entry
    data = dict(entry.data)
    for field_, original in private.items():
        kept = data.get(field_)
        # A field of members gets back the members that were masked; any other, itself.
        data[field_] = {**kept, **original} if isinstance(kept, dict) and isinstance(original, dict) else original
    return entry.model_copy(update={"data": data})


def may_be_private(kind: str) -> bool:
    """Whether an entry of this kind can carry a value its agent declared private."""
    return kind in WRITTEN_DOWN


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


def _declared(kind: str, data: JsonObject, config: AgentConfig) -> tuple[str, frozenset[str]] | None:
    if kind == CARRY_ARGUMENTS:
        spec = config.tools_by_name.get(str(data.get("name")))
        return None if spec is None else ("arguments", spec.pii)
    if kind in CARRY_STATE:
        return "state", frozenset(name for name, seen in config.state_fields.items() if seen == "pii")
    return None


@dataclass(frozen=True)
class _Secrets:
    """The private values as one pattern for strings and one set for numbers."""

    pattern: re.Pattern[str] | None
    whole: frozenset[str]

    @classmethod
    def of(cls, secrets: Sequence[str]) -> "_Secrets":
        """A value is a secret where it stands as a whole word: `Ana` is no part of `Banana` or `Anabel`.

        The longest alternative comes first, so a value that holds another is masked whole.
        """
        if not secrets:
            return cls(None, frozenset())
        ordered = sorted(secrets, key=len, reverse=True)
        words = "|".join(re.escape(secret) for secret in ordered)
        return cls(re.compile(rf"(?<!\w)(?:{words})(?!\w)"), frozenset(ordered))


# A field of members is masked member by member, so the originals kept aside are the members
# that changed; any other value is masked whole and kept whole.
def _masked(value: Json, by_name: Collection[str], secrets: _Secrets) -> tuple[Json, Json | None]:
    if not a_mapping(value):
        scrubbed = _scrubbed(value, secrets)
        return (scrubbed, value) if scrubbed != value else (value, None)
    masked: JsonObject = {}
    aside: JsonObject = {}
    for name, member in value.items():
        replaced = MASK if name in by_name else _scrubbed(member, secrets)
        if replaced != member or name in by_name:
            masked[name] = replaced
            aside[name] = member
    return ({**value, **masked}, aside) if aside else (value, None)


# A leaf that is a private value goes whole; a string that holds one as a word has it replaced, so
# the rest of what it said stays readable. What a number reads as is how a tool's argument was written.
def _scrubbed(value: Json, secrets: _Secrets) -> Json:
    if secrets.pattern is None:
        return value
    if isinstance(value, str):
        return secrets.pattern.sub(MASK, value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return MASK if str(value) in secrets.whole else value
    if isinstance(value, list):
        return [_scrubbed(item, secrets) for item in value]
    return {name: _scrubbed(member, secrets) for name, member in value.items()}


# Every string and number inside a value, as text; a blank is no secret, it would mask everything.
def _leaves(value: Json) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in _leaves(item)]
    return [leaf for member in value.values() for leaf in _leaves(member)]
