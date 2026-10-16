"""What the serve entry is told and loads: its flags, the class in a file, a state by field."""

import importlib.util
import json
import re
import sys
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path

from pinecall.agent import Agent
from pinecall.errors import DeclarationRefused, PinecallError
from pinecall.wire._names import Channel, JsonObject, Medium

# The package every served agent's folder is loaded under, so `from .agenda import …` works.
ROOT = "pinecall_agents"

CHANNELS: tuple[Channel, ...] = typing.get_args(Channel)
MEDIUMS: tuple[Medium, ...] = typing.get_args(Medium)


class CannotServe(PinecallError):
    """What was asked cannot be served at all; the entry says why and exits 2."""


@dataclass(frozen=True)
class Served:
    """One agent file, and the slug it is served as: its folder's name."""

    file: Path
    slug: str


@dataclass(frozen=True)
class Flags:
    """The flags of one verb, as the CLI passes them."""

    served: tuple[Served, ...]
    console: bool = False
    events: bool = False
    prod: bool = False
    state: JsonObject = field(default_factory=dict[str, object])  # pyright: ignore[reportAssignmentType]
    channel: Channel = "phone"
    medium: Medium | None = None
    show_machine: bool = False


def parse(argv: list[str]) -> Flags:
    """`--file` and `--slug` paired by place; the rest by name; a flag nobody declared refused."""
    files: list[str] = []
    slugs: list[str] = []
    found: dict[str, object] = {"state": {}}
    words = list(argv)
    while words:
        word = words.pop(0)
        if word in ("--file", "--slug", "--state", "--channel", "--medium"):
            value = value_of(word, words)
            if word == "--file":
                files.append(value)
            elif word == "--slug":
                slugs.append(value)
            elif word == "--state":
                typing.cast("JsonObject", found["state"]).update(as_state(value))
            else:
                found[word.removeprefix("--")] = value
        elif word in ("--console", "--events", "--prod", "--show-machine"):
            found[word.removeprefix("--").replace("-", "_")] = True
        else:
            raise CannotServe(f"serve has no flag {word}")
    if not files or len(files) != len(slugs):
        raise CannotServe("serve takes one --slug for each --file, and at least one of each")
    if found.get("channel", "phone") not in CHANNELS or found.get("medium") not in (None, *MEDIUMS):
        raise CannotServe("--channel is phone, web or whatsapp, and --medium is voice or text")
    served = tuple(Served(Path(file), slug) for file, slug in zip(files, slugs, strict=True))
    return Flags(served, **typing.cast("dict[str, typing.Any]", found))


def as_state(pair: str) -> JsonObject:
    """`field=json`: the field's value as JSON; one that is not JSON is refused by its field."""
    name, equals, value = pair.partition("=")
    if not name or not equals:
        raise CannotServe(f"--state {pair}: a field, =, and its value as JSON")
    try:
        return {name: json.loads(value)}
    except json.JSONDecodeError:
        raise CannotServe(f"--state {name}: its value is not JSON") from None


def load_served(served: Served) -> type[Agent]:
    """The class the file defines, served as its folder's slug; refused when it names another."""
    cls = load_agent(served.file)
    declared = cls.slug
    if declared is not None and declared != served.slug:
        raise CannotServe(
            f"{served.file} says its slug is {declared}, and it is served as {served.slug}:"
            " the slug is its folder's name"
        )
    # The folder names it: its view is `views/<slug>.jinja` beside it, whatever the class is called.
    cls.slug = served.slug
    return cls


def load_agent(file: Path) -> type[Agent]:
    """The last `Agent` the file defines, loaded as a module of a package that is its folder."""
    path = file.resolve()
    if not path.is_file():
        raise CannotServe(f"no agent at {path}")
    folder = re.sub(r"\W", "_", path.parent.name)
    package = f"{ROOT}.{folder}"
    named = f"{package}.{path.stem}"
    packaged(package, path.parent)
    spec = importlib.util.spec_from_file_location(named, path)
    if spec is None or spec.loader is None:
        raise CannotServe(f"{path} is not a Python file")
    module = importlib.util.module_from_spec(spec)
    sys.modules[named] = module
    try:
        spec.loader.exec_module(module)
    except DeclarationRefused:
        raise
    except Exception as failed:
        raise CannotServe(f"{path} did not load: {type(failed).__name__}: {failed}") from failed
    written = [
        one
        for one in vars(module).values()
        if isinstance(one, type) and issubclass(one, Agent) and one.__module__ == named
    ]
    if not written:
        raise CannotServe(f"{path} declares no pinecall.Agent")
    return written[-1]


def packaged(package: str, folder: Path) -> None:
    """The packages a served file is loaded under; its folder is also importable by name."""
    if ROOT not in sys.modules:
        root = types.ModuleType(ROOT)
        root.__path__ = []
        sys.modules[ROOT] = root
    if package not in sys.modules:
        held = types.ModuleType(package)
        held.__path__ = [str(folder)]
        sys.modules[package] = held
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))


def value_of(flag: str, words: list[str]) -> str:
    """The value a flag takes, refused when there is none."""
    if not words or words[0].startswith("--"):
        raise CannotServe(f"{flag} takes a value")
    return words.pop(0)
