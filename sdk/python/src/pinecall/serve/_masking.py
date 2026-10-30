"""What a served process prints of its entries: private values masked as the log masks them."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pinecall.wire._names import Json, JsonObject
from pinecall.wire.config import AgentConfig
from pinecall.wire.frames import Entry

MASK = "***"

# A value shorter than this is never learned: "7", "ok" or "Al" cannot be told from a word, and
# masking it would mask every such digit or word printed after it. The argument is still masked by
# its name.
LEAST_SECRET_CHARS = 3

# What the agent wrote down, by entry: the fields of its data a private value may be in. What was
# said is the caller's and the model's words, and never masked.
WRITTEN_DOWN: Mapping[str, tuple[str, ...]] = {
    "tool.call": ("arguments",),
    "tool.result": ("output", "error", "summary"),
    "state.changed": ("state",),
    "call.attached": ("state",),
    "custom": ("data",),
}


class Masking:
    """One agent's private names and, as its tool calls pass, the private values they carried."""

    def __init__(self, declared: AgentConfig) -> None:
        """The arguments its tools list under pii, and the state fields declared pii."""
        self._arguments = {tool.name: frozenset(tool.pii or ()) for tool in declared.tools or ()}
        self._fields = frozenset(
            field.name for field in declared.state_fields or () if field.visibility == "pii"
        )
        self._values: set[str] = set()

    def entry(self, entry: Entry) -> Entry:
        """The entry with every private value masked: by name where named, by value elsewhere."""
        fields = WRITTEN_DOWN.get(entry.type)
        if fields is None:
            return entry
        by_name = self._arguments.get(str(entry.data.get("name")), frozenset())
        if not (self._values or self._fields or (entry.type == "tool.call" and by_name)):
            return entry
        if entry.type == "tool.call":
            self._learn(by_name, entry.data)
        secrets = Secrets.of(self._values)
        data: JsonObject = dict(entry.data)
        for name in fields:
            if name in data:
                names = by_name if entry.type == "tool.call" else self._fields
                data[name] = masked(
                    data[name], names if name in ("arguments", "state") else frozenset(), secrets
                )
        return entry.model_copy(update={"data": data})

    def _learn(self, names: frozenset[str], data: JsonObject) -> None:
        given = data.get("arguments")
        if isinstance(given, dict):
            for name in names:
                self._values.update(
                    leaf for leaf in leaves(given.get(name)) if len(leaf) >= LEAST_SECRET_CHARS
                )


@dataclass(frozen=True)
class Secrets:
    """The private values as one pattern for strings and one set for numbers."""

    pattern: re.Pattern[str] | None
    whole: frozenset[str]

    @classmethod
    def of(cls, values: set[str]) -> "Secrets":
        """A value is a secret where it stands as a whole word: `Ana` is no part of `Banana`.

        The longest alternative comes first, so a value that holds another is masked whole.
        """
        if not values:
            return cls(None, frozenset())
        words = "|".join(re.escape(value) for value in sorted(values, key=len, reverse=True))
        return cls(re.compile(rf"(?<!\w)(?:{words})(?!\w)"), frozenset(values))


# A field of members is masked member by member; any other value is masked of the secrets alone.
def masked(value: Json, names: frozenset[str], secrets: Secrets) -> Json:
    """The value with the members named masked whole and every secret in the rest."""
    if not isinstance(value, dict):
        return scrubbed(value, secrets)
    return {
        name: MASK if name in names else scrubbed(member, secrets) for name, member in value.items()
    }


# A leaf that is a private value goes whole; a string that holds one as a word has it replaced.
def scrubbed(value: Json, secrets: Secrets) -> Json:
    """The value with every secret in it masked."""
    if secrets.pattern is None:
        return value
    if isinstance(value, str):
        return secrets.pattern.sub(MASK, value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return MASK if str(value) in secrets.whole else value
    if isinstance(value, list):
        return [scrubbed(item, secrets) for item in value]
    return {name: scrubbed(member, secrets) for name, member in value.items()}


# Every string and number inside a value, as text; a blank is no secret, it would mask everything.
def leaves(value: Json) -> list[str]:
    """The strings and numbers inside a value, as the text that would be masked."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in leaves(item)]
    return [leaf for member in value.values() for leaf in leaves(member)]
