"""What a call's log keeps of the values its agent declared private: masked, sealed aside, opened for the app."""

import json
import logging
import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

from runtime.agents.declaration import Declaration
from runtime.calls.log.store import Store
from runtime.exceptions import ServiceUnavailable
from runtime.kit.crypto import Vault
from runtime.kit.text import Json, JsonObject, a_list, a_mapping
from runtime.wire.base import Entry
from runtime.wire.parts import MASKED

logger = logging.getLogger(__name__)

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

# The private values of some entries, by seq, as their writer wrote them.
type Aside = list[tuple[int, JsonObject]]


@dataclass(frozen=True, slots=True)
class Split:
    """An entry's data as the log keeps it, and the values masked in it, by their field."""

    kept: JsonObject
    private: JsonObject


# ── a declaration's words on a value, with no log ──


# The key stays, so a reader knows a value exists; the value goes whole (`wire.parts.MASKED`), so
# its type does not leak.
def split(kind: str, data: JsonObject, declaration: Declaration, secrets: Sequence[str] = ()) -> Split:
    """The entry with every value its agent declared private masked, and those values apart.

    A tool's arguments and a state field are private by name; whatever else the agent wrote down
    is masked of `secrets` wherever one stands as a whole word, in a string or as a whole leaf.
    """
    fields = WRITTEN_DOWN.get(kind)
    if fields is None:
        return Split(data, {})
    found = _Secrets.of(secrets)
    named = _private_by_name(kind, data, declaration)
    kept = dict(data)
    private: JsonObject = {}
    for name in fields:
        if name not in data:
            continue
        by_name = named[1] if named is not None and named[0] == name else frozenset[str]()
        masked, aside = _mask(data[name], by_name, found)
        if aside is not None:
            kept[name] = masked
            private[name] = aside
    return Split(kept, private) if private else Split(data, {})


def mask_state(app_state: JsonObject, declaration: Declaration) -> JsonObject:
    """The app's state with every field declared pii masked."""
    return {name: MASKED if declaration.visibility_of(name) == "pii" else value for name, value in app_state.items()}


def restore(entry: Entry, private: JsonObject | None) -> Entry:
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


def seal_values(vault: Vault, values: JsonObject) -> str:
    """The private values of one entry, sealed under the vault for the store."""
    return vault.seal(json.dumps(values))


# A value sealed under a key PINECALL_VAULT_KEY no longer lists stays masked: the call goes on.
def open_values(vault: Vault, token: str | None) -> JsonObject | None:
    """The private values a sealed row holds, opened; None for no row, or a key the vault lost."""
    if token is None:
        return None
    try:
        values: Json = json.loads(vault.open(token))
    except ServiceUnavailable:
        logger.warning("a private value sealed under a key the vault no longer lists stays masked")
        return None
    return values if isinstance(values, dict) else None


def open_entries(vault: Vault, entries: Sequence[Entry], sealed: dict[int, str]) -> list[Entry]:
    """The entries as their writer wrote them, the private values kept aside opened."""
    return [restore(entry, open_values(vault, sealed.get(entry.seq))) for entry in entries]


# ── one log's privacy ──


# Held by the call's log from the moment its writer says what the agent declared (`Log.mask_by`).
# `values` are the private values the call's tool calls carried, learned as they are written or
# forwarded: every later entry the agent wrote is masked of them, wherever they appear.
class Privacy:
    """What a call's writer masks by: the vault it seals with, the declaration it reads, and the values learned."""

    def __init__(self, store: Store, log: str, vault: Vault, declaration: Declaration) -> None:
        """Nothing learned yet, nothing opened: the store holds what other gateways sealed."""
        self.vault = vault
        self.declaration = declaration
        self.values: set[str] = set()
        # The newest tool.call whose values were asked of the store, so a gateway asks for what is new.
        self.through = 0
        self._store = store
        self._log = log
        # The private values of the entries appended or opened here, by seq, for the app's socket.
        self._opened: dict[int, JsonObject] = {}

    @property
    def active(self) -> bool:
        """Whether the declaration names anything private at all: when not, nothing is masked or sealed."""
        pii_fields = any(seen == "pii" for seen in self.declaration.state_fields.values())
        return pii_fields or any(spec.pii for spec in self.declaration.tools)

    # A written call's own declaration of what is private, as the app configured it for this call.
    def declare(self, declaration: Declaration) -> None:
        """Mask by this declaration from now on; what was learned stays learned."""
        self.declaration = declaration

    def learn(self, kind: str, data: JsonObject) -> None:
        """Take the values of the arguments a tool.call lists under pii as private from here on."""
        if kind != CARRY_ARGUMENTS:
            return
        spec = self.declaration.tools_by_name.get(str(data.get("name")))
        arguments = data.get("arguments")
        if spec is None or not a_mapping(arguments):
            return
        for name in spec.pii:
            self.values.update(leaf for leaf in _leaves_of(arguments.get(name)) if len(leaf) >= LEAST_SECRET_CHARS)

    def secrets(self) -> list[str]:
        """The private values, the longest first, so one that holds another is masked whole."""
        return sorted(self.values, key=len, reverse=True)

    async def mask(self, kind: str, data: JsonObject) -> Split:
        """One entry as the log keeps it, and what was masked in it."""
        [masked] = await self.mask_all([(kind, data)])
        return masked

    # In the order they will be written: a tool.call teaches its values to the entries after it.
    async def mask_all(self, entries: Sequence[tuple[str, JsonObject]]) -> list[Split]:
        """Each entry as the log keeps it, masked of what this gateway and the others learned so far."""
        if not self.active:
            return [Split(data, {}) for _, data in entries]
        await self._learn_what_was_sealed(kind for kind, _ in entries)
        masked: list[Split] = []
        for kind, data in entries:
            self.learn(kind, data)
            masked.append(split(kind, data, self.declaration, self.secrets()))
        return masked

    # In memory before the entries are published, so the app's socket on this gateway is sent them
    # as they were written without asking the store.
    def remember(self, written: Iterable[tuple[Entry, Split]]) -> Aside:
        """Keep the values masked in these entries for the app's socket; what is to be sealed aside."""
        aside = [(entry.seq, masked.private) for entry, masked in written if masked.private]
        self._opened.update(aside)
        return aside

    async def seal_aside(self, aside: Aside) -> None:
        """Seal the values under the vault beside their entries, for every other gateway to open."""
        if aside:
            rows = [(seq, seal_values(self.vault, values)) for seq, values in aside]
            await self._store.keep_private(self._log, rows)

    async def keep(self, written: Iterable[tuple[Entry, Split]]) -> None:
        """Remember what was masked in these entries and seal it aside."""
        await self.seal_aside(self.remember(written))

    # An entry another gateway wrote has its values in that gateway's memory and in the store.
    async def open(self, entry: Entry) -> Entry:
        """The entry as its writer wrote it, for the app's socket: the private values back in."""
        values = self._opened.get(entry.seq)
        if values is None and self.active and may_be_private(entry.type):
            values = open_values(self.vault, await self._store.find_private(self._log, entry.seq))
            if values:
                self._opened[entry.seq] = values
        opened = restore(entry, values)
        self.learn(opened.type, opened.data)
        return opened

    async def open_all(self) -> list[Entry]:
        """Every entry of the log as its writer wrote it, the private values sealed aside opened."""
        entries, sealed = await self._store.whole_with_private(self._log)
        opened = open_entries(self.vault, entries, sealed)
        for entry in opened:
            self.learn(entry.type, entry.data)
        return opened

    # Another gateway may have asked the app for a tool whose arguments are private: what it sealed
    # is read before an entry that could repeat the values is written, or they would go in the clear.
    async def _learn_what_was_sealed(self, kinds: Iterable[str]) -> None:
        if not any(may_be_private(kind) for kind in kinds):
            return
        for entry, sealed in await self._store.list_private_tool_calls(self._log, self.through):
            opened = restore(entry, open_values(self.vault, sealed))
            self.learn(opened.type, opened.data)
            self.through = max(self.through, entry.seq)


# A log nobody said a declaration for: a reader's, an agent's own. It asks nothing of whoever
# holds it: until 2026-11 a log asked six times whether it had a privacy and whether it was active.
class NoPrivacy:
    """The privacy of a log nothing was declared private for: nothing masked, nothing sealed, nothing to open."""

    def __init__(self, store: Store, log: str) -> None:
        """Keep the store, for whoever asks for the whole log."""
        self._store = store
        self._log = log

    def declare(self, declaration: Declaration) -> None:
        """Nothing: no writer said what this log masks by."""

    async def mask(self, _kind: str, data: JsonObject) -> Split:
        """The entry as it is."""
        return Split(data, {})

    async def mask_all(self, entries: Sequence[tuple[str, JsonObject]]) -> list[Split]:
        """The entries as they are."""
        return [Split(data, {}) for _, data in entries]

    def remember(self, _written: Iterable[tuple[Entry, Split]]) -> Aside:
        """Nothing was masked."""
        return []

    async def seal_aside(self, aside: Aside) -> None:
        """Nothing to seal."""

    async def keep(self, written: Iterable[tuple[Entry, Split]]) -> None:
        """Nothing to keep."""

    async def open(self, entry: Entry) -> Entry:
        """The entry as the log holds it."""
        return entry

    async def open_all(self) -> list[Entry]:
        """Every entry of the log as the log holds it."""
        return await self._store.whole_of(self._log)


def _private_by_name(kind: str, data: JsonObject, declaration: Declaration) -> tuple[str, frozenset[str]] | None:
    if kind == CARRY_ARGUMENTS:
        spec = declaration.tools_by_name.get(str(data.get("name")))
        return None if spec is None else ("arguments", spec.pii)
    if kind in CARRY_STATE:
        return "state", frozenset(name for name, seen in declaration.state_fields.items() if seen == "pii")
    return None


@dataclass(frozen=True, slots=True)
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
def _mask(value: Json, by_name: Collection[str], secrets: _Secrets) -> tuple[Json, Json | None]:
    if not a_mapping(value):
        scrubbed = _scrub(value, secrets)
        return (scrubbed, value) if scrubbed != value else (value, None)
    masked: JsonObject = {}
    aside: JsonObject = {}
    for name, member in value.items():
        replaced = MASKED if name in by_name else _scrub(member, secrets)
        if replaced != member or name in by_name:
            masked[name] = replaced
            aside[name] = member
    return ({**value, **masked}, aside) if aside else (value, None)


# A leaf that is a private value goes whole; a string that holds one as a word has it replaced, so
# the rest of what it said stays readable. What a number reads as is how a tool's argument was written.
def _scrub(value: Json, secrets: _Secrets) -> Json:
    if secrets.pattern is None:
        return value
    if isinstance(value, str):
        return secrets.pattern.sub(MASKED, value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return MASKED if str(value) in secrets.whole else value
    if isinstance(value, list):
        return [_scrub(item, secrets) for item in value]
    return {name: _scrub(member, secrets) for name, member in value.items()}


# Every string and number inside a value, as text; a blank is no secret, it would mask everything.
def _leaves_of(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, int | float):
        return [str(value)]
    if a_list(value):
        return [leaf for item in value for leaf in _leaves_of(item)]
    if a_mapping(value):
        return [leaf for member in value.values() for leaf in _leaves_of(member)]
    return []
