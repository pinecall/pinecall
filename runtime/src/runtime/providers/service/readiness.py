"""What an org can run: every installed vendor and whose key runs it, and the models a picker offers of each."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.enums import Stage
from runtime.kit.crypto import Vault
from runtime.providers.catalog import Catalog, Rate, stage_key
from runtime.providers.service import plugins
from runtime.providers.service.catalog import get_catalog
from runtime.providers.service.keyring import Keyring, is_lent, keys_of
from runtime.providers.service.plugins import Vendor
from runtime.providers.service.signatures import lists_voices

type Availability = Literal["yours", "offered", "bring your own", "broken"]
type Standing = Literal["ready", "no plugin", "no key", "its own"]

# Availabilities a call can run on.
READY = frozenset({"yours", "offered"})
# v1's word for each, which the console draws: a vendor nobody keyed for this org has "no key".
STANDING: dict[Availability, Standing] = {
    "yours": "ready",
    "offered": "ready",
    "bring your own": "no key",
    "broken": "no plugin",
}


# v1's row, which the console reads, and `availability` and `broken` beside it: `standing` is
# `availability` in v1's words, and the fields v1 read off a table in code are empty here.
@dataclass(frozen=True, slots=True)
class Readiness:
    """One installed vendor as an org reads it: what it does, whose key runs it for this org, and why not."""

    name: str
    does: tuple[Stage, ...]
    availability: Availability
    broken: str | None = None
    voices_listed: bool = False

    @property
    def note(self) -> str:
        """Why the plugin does not import, or nothing."""
        return self.broken or ""

    @property
    def standing(self) -> Standing:
        """The availability in v1's words."""
        return STANDING[self.availability]

    @property
    def ready(self) -> bool:
        """Whether a call of this org can run on the vendor now."""
        return self.availability in READY

    @property
    def extra(self) -> str:
        """The plugin's extra of livekit-agents: its name."""
        return self.name


@dataclass(frozen=True, slots=True)
class Choice:
    """One model a picker offers of a vendor for a stage: its name, whether this org may run it, its price."""

    model: str
    name: str
    recommended: bool
    # On the org's own key, or lent by the platform; false where only a key of the org's own would run it.
    available: bool
    price: Rate | None


@dataclass(frozen=True, slots=True)
class Runnable:
    """Every vendor this build runs and how this org may run it, the defaults per stage, the models named."""

    providers: list[Readiness]
    defaults: Mapping[Stage, str]
    # `stt/deepgram`: the models the org may run, alone, the one that runs first leading.
    models: dict[str, list[str]]
    # `stt/deepgram`: every model the row offers of a vendor for a stage, the recommended first, each saying
    # whether this org may run it.
    choices: dict[str, list[Choice]]
    # `stt/deepgram`: the model a call runs when none is picked: the row's, else the plugin's own where
    # it says one; a vendor absent here decides inside its plugin.
    runs: dict[str, str]
    # `xai`: the models that hear and speak themselves, as the vendor's plugin lists them.
    realtime: dict[str, list[str]]


# The same for every key of an org: what is installed, and whose key would run each vendor.
async def runnable_by(session: AsyncSession, vault: Vault, scope: Scope) -> Runnable:
    """Every vendor this build runs and how the scope's org may run it, the defaults, the models named."""
    return runnable_on(await get_catalog(session), await keys_of(session, vault, scope), plugins.list_vendors())


def runnable_on(catalog: Catalog, keys: Keyring, installed: Mapping[str, Vendor]) -> Runnable:
    """Every vendor installed as these keys may run it, with the row's defaults and models."""
    runs = runs_of(catalog, installed)
    return Runnable(
        providers=list_readiness(installed, catalog, keys),
        defaults=catalog.default_vendors,
        models=_list_models_offered(catalog, keys, runs),
        choices=_list_choices(catalog, keys, runs),
        runs=runs,
        realtime={vendor.name: list(vendor.realtime) for vendor in installed.values() if vendor.realtime},
    )


def list_readiness(vendors: Mapping[str, Vendor], catalog: Catalog, keys: Keyring) -> list[Readiness]:
    """Every installed vendor, sorted, and how this org may run it."""
    return [
        Readiness(
            name=vendor.name,
            does=tuple(sorted(vendor.does)),
            availability=_availability_of(vendor, keys),
            broken=vendor.broken,
            voices_listed=lists_voices(vendor.name, vendor.does) or bool(catalog.list_voices_for(vendor.name)),
        )
        for vendor in sorted(vendors.values(), key=lambda one: one.name)
    ]


# The model a call on a vendor runs when none is picked, in the order a stage takes it: the
# row's for that vendor, else the platform default's where the default is that vendor, else the one
# the plugin builds where its constructor says one — which a call never runs on the default's vendor.
def runs_of(catalog: Catalog, installed: Mapping[str, Vendor]) -> dict[str, str]:
    """By `stage/vendor`, the model that runs when none is picked, where it is known."""
    runs = {
        stage_key(stage, vendor.name): model
        for vendor in installed.values()
        for stage, model in vendor.defaults.items()
    }
    for stage, default in catalog.defaults.items():
        if default.model:
            runs[stage_key(stage, default.vendor)] = default.model
    runs.update(catalog.models)
    return runs


# What a picker offers this org of each vendor and stage: the one that runs first, then the models the
# row offers, kept to what the box lends the org where it lends by model (an entry names no stage, so
# a model the row does not list is offered nowhere). On the org's own key, every one.
def _list_models_offered(catalog: Catalog, keys: Keyring, runs: Mapping[str, str]) -> dict[str, list[str]]:
    offered: dict[str, list[str]] = {}
    for named, vendor, listed in _list_per_stage(catalog, runs):
        if vendor not in keys.own and keys.lends is not None and vendor not in keys.lends:
            listed = [model for model in listed if is_lent(keys.lends, vendor, model)]
        if listed:
            offered[named] = listed
    return offered


# Every model the row offers of each vendor and stage, the recommended first and then the one that runs
# first and the rest in the row's order, each saying whether this org may run it: on its own key any, on the
# box's what is lent; a picker draws the others greyed, for the org to bring its key.
def _list_choices(catalog: Catalog, keys: Keyring, runs: Mapping[str, str]) -> dict[str, list[Choice]]:
    choices: dict[str, list[Choice]] = {}
    for named, vendor, listed in _list_per_stage(catalog, runs):
        leads = [model for model in catalog.recommended.get(named, ()) if model in listed]
        ordered = [*leads, *(model for model in listed if model not in leads)]
        if ordered:
            choices[named] = [
                Choice(
                    model=model,
                    name=catalog.name_of(vendor, model),
                    recommended=model in leads,
                    available=keys.may_run(vendor, model),
                    price=catalog.rate_for(model),
                )
                for model in ordered
            ]
    return choices


# Each `stage/vendor` of the row with its models, the one that runs first leading, each once.
def _list_per_stage(catalog: Catalog, runs: Mapping[str, str]) -> list[tuple[str, str, list[str]]]:
    return [
        (named, vendor, list(dict.fromkeys([*([runs[named]] if named in runs else []), *offered])))
        for named, vendor, offered in catalog.per_stage()
    ]


def _availability_of(vendor: Vendor, keys: Keyring) -> Availability:
    if vendor.broken is not None:
        return "broken"
    if vendor.name in keys.own:
        return "yours"
    if vendor.name in keys.box and keys.lends_any_of(vendor.name):
        return "offered"
    return "bring your own"
