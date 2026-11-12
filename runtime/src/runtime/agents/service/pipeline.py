"""An agent's pipeline: the stages a worker is handed on their keys, and what its next call would run, to read."""

import dataclasses
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Actor, Scope
from runtime.agents.declaration import Agent, Declaration, Greeting
from runtime.agents.service.settings import Picked, resolve_for_call
from runtime.enums import KeyScope, Stage
from runtime.exceptions import PinecallError
from runtime.kit.crypto import Vault
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.providers.stage import Running, primary_language


# Which vendors are failing now is counted where the calls' errors are written, above this domain:
# whatever counts them is handed in.
class VendorHealth(Protocol):
    """The vendors over their error line now, and the count of the calls handed each."""

    def failing(self, at: float) -> frozenset[str]:
        """The vendors over their error line in the window up to now."""
        ...

    def count_handed(self, vendors: Iterable[str], at: float) -> None:
        """A call's stages were resolved with these vendors first, each counted once."""
        ...


# The latencies of an agent's last calls are folded from their logs, above this domain: the report
# carries what it is handed.
class Median(Protocol):
    """One latency over an agent's recent calls: livekit's name, the median, the turns."""

    @property
    def name(self) -> str:
        """Livekit's name for the latency."""
        ...

    @property
    def seconds(self) -> float:
        """Its median."""
        ...

    @property
    def turns(self) -> int:
        """The turns it was measured over."""
        ...


@dataclass(frozen=True, slots=True)
class Measured:
    """How fast an agent's last calls ran: how many were pooled, and each latency's median."""

    calls: int = 0
    medians: Sequence[Median] = ()


@dataclass(frozen=True, slots=True)
class WorkerStages:
    """The stages a call of the agent runs, each on its key, and the org's collector."""

    llm: Running
    stt: Running
    tts: Running
    # A voice call's whole conversation, where the agent names a model that hears and speaks itself.
    realtime: Running | None = None
    telemetry: providers.Telemetry | None = None


@dataclass(frozen=True, slots=True)
class StagePlan:
    """One stage as the next call would run it: the vendor, its model, the voice or language."""

    vendor: str
    model: str | None = None
    voice_id: str | None = None
    language: str | None = None


# The answer is flat, as GET /v1/providers is: what the org can run is read off `runnable`, and how fast
# its calls ran off `measured`, each under the name the answer gives it.
@dataclass(frozen=True, slots=True)
class Report:
    """What an agent hears, decides and speaks with, what its org could run instead, and how fast its calls ran."""

    agent: str
    hears: StagePlan
    decides: StagePlan
    speaks: StagePlan
    # What a voice call runs on alone, where the agent names a model that hears and speaks itself.
    talks: StagePlan | None
    greeting: Greeting | None
    runnable: providers.Runnable
    # By vendor and language (`google/en`), the voice a call speaks when none is picked: the row's.
    voice_defaults: Mapping[str, str]
    measured: Measured
    # Which stage has no key to run on, and why, before a call fails for want of it.
    unavailable_reasons: Mapping[str, str] = field(default_factory=dict[str, str])
    # The picker reads GET /v1/voices; no names are curated in code.
    voices: tuple[str, ...] = ()

    @property
    def providers(self) -> Sequence[object]:
        """Every installed vendor and how this org may run it."""
        return self.runnable.providers

    @property
    def defaults(self) -> Mapping[Stage, str]:
        """The vendor each stage runs by default."""
        return self.runnable.defaults

    @property
    def models(self) -> Mapping[str, Sequence[str]]:
        """By stage and vendor, the models the org may run."""
        return self.runnable.models

    @property
    def choices(self) -> Mapping[str, Sequence[object]]:
        """By stage and vendor, every model the row offers, each saying whether this org may run it."""
        return self.runnable.choices

    @property
    def runs(self) -> Mapping[str, str]:
        """By stage and vendor, the model a call runs when none is picked."""
        return self.runnable.runs

    @property
    def realtime(self) -> Mapping[str, Sequence[str]]:
        """By vendor, the models that hear and speak themselves."""
        return self.runnable.realtime

    @property
    def calls(self) -> int:
        """How many of its last calls the medians pool."""
        return self.measured.calls

    @property
    def medians(self) -> Sequence[Median]:
        """Each latency's median over those calls."""
        return self.measured.medians


# The one answer that carries keys: to the fleet's key, or the org's own worker's. The box's keys
# leave it only for its own workers: an org's process is handed the org's keys alone.
async def stages_for_worker(
    session: AsyncSession,
    vault: Vault,
    actor: Actor,
    declaration: Declaration,
    health: VendorHealth,
    *,
    picked: Picked | None = None,
    test: Mapping[str, Any] | None = None,
) -> WorkerStages:
    """The three stages a call of the agent runs, each on its key, the vendors failing now last, and the collector."""
    catalog = await providers.get_catalog(session)
    resolved = await resolve_for_call(session, declaration, actor.scope, catalog, picked, test)
    keys = await providers.keys_of(session, vault, actor.scope)
    if not actor.opens(KeyScope.fleet):
        keys = dataclasses.replace(keys, lends=frozenset())
    at = time.monotonic()
    stages = providers.build_pipeline(resolved.declaration, catalog, keys).demoting(health.failing(at))
    health.count_handed((stages.llm.vendor, stages.stt.vendor, stages.tts.vendor), at)
    traced = await providers.telemetry_of(session, vault, actor.org)
    return WorkerStages(stages.llm, stages.stt, stages.tts, stages.realtime, traced)


# Nothing is built: a vendor without a key is a reason, not a failure.
async def report_on(session: AsyncSession, vault: Vault, scope: Scope, agent: Agent, measured: Measured) -> Report:
    """The agent's three stages as its next call in the scope would run them, the catalogue, and its latencies."""
    catalog = await providers.get_catalog(session)
    resolved = (await resolve_for_call(session, agent.whole, scope, catalog)).declaration
    keys = await providers.keys_of(session, vault, scope)
    language = primary_language(resolved.language)
    stages = {
        "hears": _plan_stage(Stage.stt, resolved, catalog, language=language),
        "decides": _plan_stage(Stage.llm, resolved, catalog, language=None),
        "speaks": _plan_stage(Stage.tts, resolved, catalog, language=language),
    }
    talks = resolved.realtime
    return Report(
        agent=agent.slug,
        hears=stages["hears"],
        decides=stages["decides"],
        speaks=stages["speaks"],
        talks=None if talks is None else StagePlan(vendor=talks.vendor, model=talks.model or None),
        greeting=resolved.greeting,
        runnable=providers.runnable_on(catalog, keys),
        voice_defaults=dict(catalog.voices),
        measured=measured,
        unavailable_reasons=_list_unavailable(stages, keys),
    )


def _plan_stage(stage: Stage, declaration: Declaration, catalog: Catalog, *, language: str | None) -> StagePlan:
    default = catalog.defaults[stage]
    if stage is Stage.tts:
        voice = declaration.voice
        return StagePlan(
            vendor=default.vendor if voice is None else voice.vendor,
            model=None if voice is None else voice.model,
            voice_id=None if voice is None else voice.voice_id,
            language=language,
        )
    named = declaration.stt if stage is Stage.stt else declaration.llm
    return StagePlan(
        vendor=default.vendor if named is None else named.vendor,
        model=None if named is None else named.model or None,
        language=language,
    )


def _list_unavailable(stages: Mapping[str, StagePlan], keys: providers.Keyring) -> dict[str, str]:
    missing: dict[str, str] = {}
    for where, stage in stages.items():
        try:
            providers.running_on(keys, stage.vendor, stage.model)
        except PinecallError as refused:
            missing[where] = str(refused)
    return missing
