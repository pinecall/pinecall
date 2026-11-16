"""The vendors' keys `setup` runs on: each choice's, found in the environment or a shell file, else asked."""

import os
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from runtime.cli.setup.choices import Choices, is_local, vendor_of
from runtime.exceptions import ValidationError
from runtime.providers.service import machine, plugins, signatures

# What the local servers ask for a key: nothing; the plugin wants one, so the org holds this word.
NO_KEY_NEEDED = "local"
# Where a key came from, when it was neither in the environment nor in a shell file.
TYPED = "typed"
# How a missing key is asked for at a terminal: the variable's name in, the secret out.
type Ask = Callable[[str], Awaitable[str]]


async def keys_for(
    choices: Choices,
    *,
    ask: Ask | None,
    environ: Mapping[str, str] = os.environ,
    home: Path | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Each chosen vendor's key, from its variable, else a shell file, else asked once; and where each one came from."""
    given: dict[str, str] = {}
    found: dict[str, str] = {}
    for vendor in sorted(choices.vendors):
        if not signatures.takes_a_key(vendor):
            continue
        variable = machine.key_variable(vendor)
        secret, where = _read_key(variable, environ, home)
        if not secret and ask is not None:
            secret, where = (await ask(variable)).strip(), TYPED
        if not secret or where is None:
            raise ValidationError(f"{vendor} needs a key: set {variable}, or answer when asked at a terminal")
        given[vendor], found[variable] = secret, where
    # The embedder is local, on the openai plugin, whatever the stages: the plugin wants a key.
    given.setdefault("openai", NO_KEY_NEEDED)
    return given, found


def keys_found(
    *, environ: Mapping[str, str] = os.environ, home: Path | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Every installed vendor whose key is in the environment or a shell file, its key read; and where each one was."""
    given: dict[str, str] = {}
    found: dict[str, str] = {}
    for vendor, plugin in sorted(plugins.list_vendors().items()):
        if plugin.broken is not None or not signatures.takes_a_key(vendor):
            continue
        variable = machine.key_variable(vendor)
        secret, where = _read_key(variable, environ, home)
        if secret and where is not None:
            given[vendor], found[variable] = secret, where
    return given, found


def say_keys(loaded: Mapping[str, str], found: Mapping[str, str], *, server: bool) -> str:
    """The vendors whose keys were found, where, and that the runtime lends them; or how to add one."""
    if not loaded:
        return "  keys      none found — `pinecall providers add <vendor>` adds one"
    places = sorted(set(found.values()), key=lambda place: (place != machine.THE_ENVIRONMENT, place))
    lent = "lent to every org" if server else "lent to your orgs"
    return f"  keys      {' · '.join(sorted(loaded))} — found in {' and '.join(places)}, {lent}"


def say_models(choices: Choices, *, card: bool = False, keyed: bool = True) -> str:
    """The open models this machine serves: an agent naming none runs on them."""
    served = [
        *choices.local_models,
        *(["whisper"] if is_local(choices.stt) else []),
        *(["kokoro"] if is_local(choices.tts) else []),
    ]
    if not served:
        on = "the keys above" if keyed else "a vendor's key for each stage"
        return f"  models    none served here — calls run on {on}"
    return f"  models    {' · '.join(served)} — open, served here{' on the GPU' if card else ''}"


# Said before the first key is asked for, so a person who came with none reads what is wanted of them
# and why: until 2026-11-16 they read a bare `ANTHROPIC_API_KEY:` under "calls run on the keys above",
# and nothing said two more were coming.
def say_asked(choices: Choices, *, environ: Mapping[str, str] = os.environ, home: Path | None = None) -> str | None:
    """The keys found nowhere, each with what its vendor does in a call; None when every one was found."""
    doing: dict[str, str] = {}
    stages = (("hears", choices.stt), ("thinks", choices.llm), ("speaks", choices.tts))
    for does, choice in (*stages, ("judges", choices.judging), ("plays the caller", choices.calling)):
        if not is_local(choice):
            doing.setdefault(vendor_of(choice), does)
    missing = [
        vendor
        for vendor in sorted(choices.vendors)
        if signatures.takes_a_key(vendor) and not _read_key(machine.key_variable(vendor), environ, home)[0]
    ]
    if not missing:
        return None
    wanted = " · ".join(f"{vendor} {doing[vendor]}" for vendor in missing)
    count = f"{len(missing)} key{'' if len(missing) == 1 else 's'}"
    said = f"  asking    {count} found nowhere — {wanted}: typed below, nothing shown"
    if len(missing) > 1 and vendor_of(choices.llm) in missing:
        said += "\n            written calls alone need the one that thinks: pinecall-runtime setup --chat-only"
    return said


# A variable's value and where it was: the environment, else the shell file setting it as plain
# text; (None, the file) when the file's line expands, (None, None) when it is nowhere.
def _read_key(variable: str, environ: Mapping[str, str], home: Path | None) -> tuple[str | None, str | None]:
    where = machine.where_is_key(variable, environ, home)
    if where == machine.THE_ENVIRONMENT:
        return environ.get(variable, "").strip(), where
    if where is not None:
        return machine.key_from_shell(variable, home), where
    return None, None
