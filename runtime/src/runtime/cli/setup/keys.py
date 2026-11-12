"""The vendors' keys `setup` runs on: each choice's, found in the environment or a shell file, else asked."""

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from runtime.cli.setup.choices import Choices, is_local
from runtime.exceptions import ValidationError
from runtime.providers.service import machine, plugins, signatures

# What the local servers ask for a key: nothing; the plugin wants one, so the org holds this word.
NO_KEY_NEEDED = "local"
# Where a key came from, when it was neither in the environment nor in a shell file.
TYPED = "typed"
# How a missing key is asked for at a terminal: the variable's name in, the secret out.
type Ask = Callable[[str], str]


def keys_for(
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
            secret, where = ask(variable).strip(), TYPED
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


def say_models(choices: Choices, *, card: bool = False) -> str:
    """The open models this machine serves: an agent naming none runs on them."""
    served = [
        *choices.local_models,
        *(["whisper"] if is_local(choices.stt) else []),
        *(["kokoro"] if is_local(choices.tts) else []),
    ]
    if not served:
        return "  models    none served here — calls run on the keys above"
    return f"  models    {' · '.join(served)} — open, served here{' on the GPU' if card else ''}"


# A variable's value and where it was: the environment, else the shell file setting it as plain
# text; (None, the file) when the file's line expands, (None, None) when it is nowhere.
def _read_key(variable: str, environ: Mapping[str, str], home: Path | None) -> tuple[str | None, str | None]:
    where = machine.where_is_key(variable, environ, home)
    if where == machine.THE_ENVIRONMENT:
        return environ.get(variable, "").strip(), where
    if where is not None:
        return machine.key_from_shell(variable, home), where
    return None, None
