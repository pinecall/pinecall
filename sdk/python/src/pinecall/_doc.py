"""A docstring as the model reads it: its description on one line, and what `Args:` says of each."""

import inspect
import re

# A Google-style section header: the description ends at the first one, as a JSDoc's ends at `@`.
SECTION = re.compile(
    r"^(Args|Arguments|Parameters|Params|Returns?|Raises|Yields|Examples?|Notes?|Attributes|"
    r"See Also|Warnings?|Todo):\s*$"
)
ARGUMENTS = ("Args", "Arguments", "Parameters", "Params")
# `name: what it is`, or `name (type): what it is`.
ENTRY = re.compile(r"^(\s+)(\w+)(?:\s*\([^)]*\))?:\s*(.*)$")


def one_line(doc: str | None) -> str | None:
    """The description before the first section, blank lines dropped, joined into one line."""
    if doc is None:
        return None
    said: list[str] = []
    for line in inspect.cleandoc(doc).splitlines():
        if SECTION.match(line):
            break
        if line.strip():
            said.append(line.strip())
    return " ".join(said) or None


def arguments_of(doc: str | None) -> dict[str, str]:
    """What the `Args:` section says of each parameter, its continuation lines joined."""
    found: dict[str, str] = {}
    if doc is None:
        return found
    inside, indent, current = False, None, None
    for line in inspect.cleandoc(doc).splitlines():
        if SECTION.match(line):
            inside, indent, current = line.split(":")[0] in ARGUMENTS, None, None
            continue
        entry = ENTRY.match(line) if inside else None
        if entry is not None and indent in (None, len(entry[1])):
            indent, current = len(entry[1]), entry[2]
            found[current] = entry[3].strip()
        elif inside and current is not None and line.strip():
            found[current] = f"{found[current]} {line.strip()}".strip()
    return found
