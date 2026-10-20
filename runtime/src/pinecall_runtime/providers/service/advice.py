"""What a host advises an org to run, stage by stage: the open models it serves, what it lends, the org's keys."""

import asyncio
import json
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.kit.text import a_list, a_mapping
from pinecall_runtime.providers.schemas import Catalog, Stage
from pinecall_runtime.providers.service.keyring import Keyring, is_lent
from pinecall_runtime.providers.service.machine import MEASURED
from pinecall_runtime.providers.service.plugins import installed

# Whose key a stage would run on: an open model this host serves (none), one the host lends, the
# org's own, or one the org has yet to bring.
type RunsOn = Literal["served here", "lent by the runtime", "your org's key", "needs a key"]
STAGES: tuple[Modality, ...] = ("stt", "llm", "tts")
# Where a stage's server is said to be in the row: an OpenAI-compatible server lists its models.
BASE_URL = "base_url"
LISTED_WITHIN_S = 3.0
THIS_HOST = frozenset({"localhost", "127.0.0.1", "::1"})

# What the models of a server at a base_url are; an empty tuple when it does not answer.
type Lister = Callable[[str], Awaitable[tuple[str, ...]]]


@dataclass(frozen=True, slots=True)
class Advised:
    """One stage's advice: the choice an agent names, whose key it runs on, and what the host serves for it."""

    stage: Modality
    choice: str
    runs_on: RunsOn
    served: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Served:
    """The open models each stage's server lists, and whether those servers are on this host."""

    models: Mapping[Modality, tuple[str, ...]] = field(default_factory=dict[Modality, tuple[str, ...]])
    on_this_host: bool = False


async def served_by(catalog: Catalog, listed: Lister | None = None) -> Served:
    """The models the row's own servers list, a stage at a time; a server that does not answer lists none."""
    ask = listed or _listed
    models: dict[Modality, tuple[str, ...]] = {}
    here = False
    for stage in STAGES:
        url = _base_url(catalog, stage)
        if url is None:
            continue
        models[stage] = await ask(url)
        here = here or urllib.parse.urlparse(url).hostname in THIS_HOST
    return Served(models, here)


def advise(catalog: Catalog, keys: Keyring, served: Served) -> list[Advised]:
    """Each stage's best: a model served here, else a vendor the host lends, else the org's own, else one to bring."""
    return [_stage(stage, catalog, keys, served) for stage in STAGES]


# ── private ──


def _stage(stage: Modality, catalog: Catalog, keys: Keyring, served: Served) -> Advised:
    default = catalog.defaults.get(stage)
    listed = served.models.get(stage, ())
    if default is not None and listed:
        return Advised(stage, f"{default.vendor}/{_best_served(stage, default, listed)}", "served here", listed)
    doing = _vendors_doing(stage, default)
    lent = [vendor for vendor in doing if vendor in keys.box and is_lent(keys.lends, vendor, None)]
    if lent:
        return Advised(stage, _named(lent[0], stage, catalog), "lent by the runtime")
    own = [vendor for vendor in doing if vendor in keys.own and _base_url(catalog, stage, vendor) is None]
    if own:
        return Advised(stage, _named(own[0], stage, catalog), "your org's key")
    vendor = default.vendor if default is not None else (doing[0] if doing else "")
    return Advised(stage, _named(vendor, stage, catalog) if vendor else "", "needs a key")


# The thinking: the best measured model the server lists, else the row's own, else the first listed.
def _best_served(stage: Modality, default: Stage, listed: tuple[str, ...]) -> str:
    if stage == "llm":
        best = next((one["model"] for one in MEASURED if one["model"] in listed), None)
        if best is not None:
            return str(best)
    return default.model if default.model in listed else listed[0]


# The row's default vendor first, then every other installed vendor that does the stage.
def _vendors_doing(stage: Modality, default: Stage | None) -> list[str]:
    others = sorted(name for name, vendor in installed().items() if vendor.broken is None and stage in vendor.does)
    first = [default.vendor] if default is not None and default.vendor in others else []
    return first + [name for name in others if name not in first]


def _named(vendor: str, stage: Modality, catalog: Catalog) -> str:
    default = catalog.defaults.get(stage)
    model = catalog.models.get(f"{stage}/{vendor}") or (
        default.model if default is not None and default.vendor == vendor else None
    )
    return f"{vendor}/{model}" if model else vendor


def _base_url(catalog: Catalog, stage: Modality, vendor: str | None = None) -> str | None:
    default = catalog.defaults.get(stage)
    named = vendor or (default.vendor if default is not None else None)
    tuned = catalog.tuning.get(f"{stage}/{named}") if named else None
    url = tuned.options.get(BASE_URL) if tuned is not None else None
    return url if isinstance(url, str) and url else None


async def _listed(url: str) -> tuple[str, ...]:
    def read() -> tuple[str, ...]:
        try:
            with urllib.request.urlopen(f"{url.rstrip('/')}/models", timeout=LISTED_WITHIN_S) as answer:
                body: object = json.load(answer)
        except (OSError, ValueError):
            return ()
        data = body.get("data") if a_mapping(body) else None
        if not a_list(data):
            return ()
        return tuple(str(one["id"]) for one in data if a_mapping(one) and "id" in one)

    return await asyncio.to_thread(read)
