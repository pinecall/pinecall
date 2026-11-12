"""What a host advises an org to run, stage by stage: the open models it serves, what it lends, the org's keys."""

import asyncio
import json
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.enums import Stage
from runtime.kit.crypto import Vault
from runtime.kit.text import a_list, a_mapping
from runtime.providers.catalog import Catalog, StageChoice, model_key
from runtime.providers.service import machine
from runtime.providers.service.catalog import get_catalog
from runtime.providers.service.keyring import Keyring, is_lent, keys_of
from runtime.providers.service.plugins import list_vendors

# Whose key a stage would run on: an open model this host serves (none), one the host lends, the
# org's own, or one the org has yet to bring.
type RunsOn = Literal["served here", "lent by the runtime", "your org's key", "needs a key"]
# Where a stage's server is said to be in the row: an OpenAI-compatible server lists its models.
BASE_URL = "base_url"
LISTED_WITHIN_S = 3.0
THIS_HOST = frozenset({"localhost", "127.0.0.1", "::1"})

# What the models of a server at a base_url are; an empty tuple when it does not answer.
type Lister = Callable[[str], Awaitable[tuple[str, ...]]]


@dataclass(frozen=True, slots=True)
class Advised:
    """One stage's advice: the choice an agent names, whose key it runs on, and what the host serves for it."""

    stage: Stage
    choice: str
    runs_on: RunsOn
    served: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Served:
    """The open models each stage's server lists, and whether those servers are on this host."""

    models: Mapping[Stage, tuple[str, ...]] = field(default_factory=dict[Stage, tuple[str, ...]])
    on_this_host: bool = False


@dataclass(frozen=True, slots=True)
class Advice:
    """What this host advises the org to run, and, for its operator, the machine."""

    stages: list[Advised]
    # What the host lends: None lends every vendor whose key it holds, empty lends nothing.
    lends: list[str] | None
    judge: str | None
    caller: str | None
    # The machine the gateway runs on, as `setup --recommend` reads it.
    machine: dict[str, Any] | None


# `pinecall login` asks this once signed in: the host advises from what it serves and lends, and the
# org's own keys. The machine is its operator's to see, and only where the row's open-model servers
# are on this same host and the box was told what was measured.
async def advise_for(session: AsyncSession, vault: Vault, scope: Scope, *, operator: bool) -> Advice:
    """What this host advises the org to run, stage by stage, and whose key each runs on."""
    catalog = await get_catalog(session)
    keys = await keys_of(session, vault, scope)
    served = await list_served(catalog)
    measured = await machine.find_measured(session) if operator and served.on_this_host else None
    return Advice(
        stages=advise(catalog, keys, served),
        lends=None if keys.lends is None else sorted(keys.lends),
        judge=catalog.judge.llm.named if catalog.judge else None,
        caller=catalog.caller.llm.named if catalog.caller and catalog.caller.llm else None,
        # Read in a thread: a subprocess, two sockets and the shell's files. Until 2026-11 it ran on the
        # event loop, and no request of the gateway was answered while `nvidia-smi` was.
        machine=None if measured is None else await asyncio.to_thread(machine.recommendation, measured),
    )


async def list_served(catalog: Catalog, listed: Lister | None = None) -> Served:
    """The models the row's own servers list, a stage at a time; a server that does not answer lists none."""
    ask = listed or _list_models
    models: dict[Stage, tuple[str, ...]] = {}
    here = False
    for stage in Stage:
        url = _base_url(catalog, stage)
        if url is None:
            continue
        models[stage] = await ask(url)
        here = here or urllib.parse.urlparse(url).hostname in THIS_HOST
    return Served(models, here)


def advise(catalog: Catalog, keys: Keyring, served: Served) -> list[Advised]:
    """Each stage's best: a model served here, else a vendor the host lends, else the org's own, else one to bring."""
    return [_advise_stage(stage, catalog, keys, served) for stage in Stage]


# ── private ──


def _advise_stage(stage: Stage, catalog: Catalog, keys: Keyring, served: Served) -> Advised:
    default = catalog.defaults.get(stage)
    listed = served.models.get(stage, ())
    if default is not None and listed:
        best = _best_served(stage, default, listed, catalog)
        return Advised(stage, model_key(default.vendor, best), "served here", listed)
    doing = _vendors_doing(stage, default)
    lent = [vendor for vendor in doing if vendor in keys.box and is_lent(keys.lends, vendor, None)]
    if lent:
        return Advised(stage, _name(lent[0], stage, catalog), "lent by the runtime")
    own = [vendor for vendor in doing if vendor in keys.own and _base_url(catalog, stage, vendor) is None]
    if own:
        return Advised(stage, _name(own[0], stage, catalog), "your org's key")
    vendor = default.vendor if default is not None else (doing[0] if doing else "")
    return Advised(stage, _name(vendor, stage, catalog) if vendor else "", "needs a key")


# The thinking: the first model the row leads with that the server lists, else the row's own, else the
# first listed. Which model is best is the row's word (the models file's `recommended`), never a table
# in code.
def _best_served(stage: Stage, default: StageChoice, listed: tuple[str, ...], catalog: Catalog) -> str:
    if stage is Stage.llm:
        best = next((model for model in catalog.leads_for(stage, default.vendor) if model in listed), None)
        if best is not None:
            return best
    return default.model if default.model in listed else listed[0]


# The row's default vendor first, then every other installed vendor that does the stage.
def _vendors_doing(stage: Stage, default: StageChoice | None) -> list[str]:
    others = sorted(name for name, vendor in list_vendors().items() if vendor.broken is None and stage in vendor.does)
    first = [default.vendor] if default is not None and default.vendor in others else []
    return first + [name for name in others if name not in first]


def _name(vendor: str, stage: Stage, catalog: Catalog) -> str:
    model = catalog.model_for(stage, vendor)
    return model_key(vendor, model) if model else vendor


def _base_url(catalog: Catalog, stage: Stage, vendor: str | None = None) -> str | None:
    default = catalog.defaults.get(stage)
    named = vendor or (default.vendor if default is not None else None)
    tuned = catalog.options_for(stage, named) if named else None
    url = tuned.options.get(BASE_URL) if tuned is not None else None
    return url if isinstance(url, str) and url else None


async def _list_models(url: str) -> tuple[str, ...]:
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
