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
from runtime.providers.stage import Running, check_languages, languages_of

# The two stages a call's languages reach, under the names the report gives them.
SPOKEN = {"hears": Stage.stt, "speaks": Stage.tts}
STAGE_OF = {**SPOKEN, "decides": Stage.llm}
# What each of them does with a language, for the sentence that says it does not.
VERB_OF = {Stage.stt: "hear", Stage.tts: "speak"}


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
    # The languages the ears listen for, and the ones the voice is asked to speak.
    languages: tuple[str, ...] = ()


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
    # Which stage runs but not well, and why: ears that do not hear the agent's languages, a voice that
    # does not speak them.
    warnings: Mapping[str, str] = field(default_factory=dict[str, str])
    # The languages the agent's callers speak, the main one first; none where it says none.
    languages: tuple[str, ...] = ()
    # By stage (`hears`, `speaks`), the row's own that take every one of those languages, in its order,
    # each with why this org cannot run it.
    suited: Mapping[str, Sequence[providers.Suited]] = field(default_factory=dict[str, Sequence[providers.Suited]])
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
async def report_on(
    session: AsyncSession, vault: Vault, scope: Scope, agent: Agent, measured: Measured, *, language: str | None = None
) -> Report:
    """The agent's three stages as its next call in the scope would run them, the catalogue, and its latencies."""
    catalog = await providers.get_catalog(session)
    resolved = (await resolve_for_call(session, agent.whole, scope, catalog)).declaration
    # Asked in languages it is not set to: answered as if it were, nothing kept.
    if language is not None:
        check_languages(language)
        resolved = dataclasses.replace(resolved, language=language)
    keys = await providers.keys_of(session, vault, scope)
    languages = languages_of(resolved.language)
    talks = resolved.realtime
    return Report(
        agent=agent.slug,
        hears=_plan_stage(Stage.stt, resolved, catalog, keys),
        decides=_plan_stage(Stage.llm, resolved, catalog, keys),
        speaks=_plan_stage(Stage.tts, resolved, catalog, keys),
        talks=None if talks is None else StagePlan(vendor=talks.vendor, model=talks.model or None),
        greeting=resolved.greeting,
        runnable=providers.runnable_on(catalog, keys, providers.list_vendors()),
        voice_defaults=dict(catalog.voices),
        measured=measured,
        unavailable_reasons=list_unavailable(resolved, catalog, keys),
        warnings=list_warnings(resolved, catalog, keys),
        languages=languages,
        suited={where: providers.list_suited(stage, languages, catalog, keys) for where, stage in SPOKEN.items()}
        if languages
        else {},
    )


def _plan_stage(stage: Stage, declaration: Declaration, catalog: Catalog, keys: providers.Keyring) -> StagePlan:
    languages = languages_of(declaration.language)
    main = languages[0] if languages else None
    if stage is Stage.llm:
        named = declaration.llm
        default = catalog.defaults[stage]
        return StagePlan(
            vendor=default.vendor if named is None else named.vendor,
            model=None if named is None else named.model or None,
        )
    vendor, model, said = _find_running(stage, declaration, catalog, keys)
    if stage is Stage.tts:
        voice = declaration.voice
        return StagePlan(vendor, said, None if voice is None else voice.voice_id, main, languages)
    listened = tuple(one for one in languages or catalog.hints if not catalog.lacks(stage, vendor, model, (one,)))
    return StagePlan(vendor, said, None, main, listened)


# A stage nobody named is the default's, said with no model, or the row's for the call's languages,
# said whole.
def _find_running(
    stage: Stage, declaration: Declaration, catalog: Catalog, keys: providers.Keyring
) -> tuple[str, str | None, str | None]:
    """The vendor and the model a stage of the agent runs, and the model as the report says it."""
    named = declaration.stt if stage is Stage.stt else declaration.voice
    if named is not None:
        return named.vendor, named.model or None, named.model or None
    chosen = providers.choose_for(stage, languages_of(declaration.language), catalog, keys)
    return chosen.vendor, chosen.model, None if chosen is catalog.defaults[stage] else chosen.model


# Checked as the call builds it (`providers.stage_on_its_key`): the vendor the agent names or the row's, on
# the model named or the one the row runs for that vendor. Until 2026-11-16 a stage with no model named was
# checked with none, so an org lent the row's own models by name (every new org) read "google is not lent to
# this org" for an agent whose calls ran on those very models.
def list_unavailable(declaration: Declaration, catalog: Catalog, keys: providers.Keyring) -> dict[str, str]:
    """Each stage the next call could not run, with the reason; empty when all three run."""
    languages = languages_of(declaration.language)
    named = {"hears": declaration.stt, "decides": declaration.llm, "speaks": declaration.voice}
    missing: dict[str, str] = {}
    for where, own in named.items():
        stage = STAGE_OF[where]
        default = providers.choose_for(stage, languages, catalog, keys)
        vendor, model = (default.vendor, default.model) if own is None else (own.vendor, own.model or None)
        try:
            providers.running_on(keys, vendor, model or catalog.model_for(stage, vendor))
        except PinecallError as refused:
            missing[where] = str(refused)
    return missing


# A call that is not heard is not refused: it runs, and its agent answers what nobody said. Said here,
# where the agent is set, in the words that fix it.
def list_warnings(declaration: Declaration, catalog: Catalog, keys: providers.Keyring) -> dict[str, str]:
    """Each stage that runs but not well, with the reason: ears or a voice that do not take the agent's languages."""
    languages = languages_of(declaration.language)
    warned: dict[str, str] = {}
    for where, stage in SPOKEN.items():
        vendor, model, _ = _find_running(stage, declaration, catalog, keys)
        if languages and not catalog.takes(stage, vendor, model, languages):
            wrong = _say_untaken(stage, vendor, model, languages, catalog)
            warned[where] = f"{wrong}: {_say_fix(stage, languages, catalog, keys)}"
    return warned


def _say_untaken(stage: Stage, vendor: str, model: str | None, languages: Sequence[str], catalog: Catalog) -> str:
    whose = f"{vendor}/{model or catalog.model_for(stage, vendor)}"
    lacking = catalog.lacks(stage, vendor, model, languages)
    if not lacking:
        return f"{whose} {VERB_OF[stage]}s one language a call, and this agent's callers speak {', '.join(languages)}"
    listed = catalog.find_languages(stage, vendor, model) or ()
    return f"{whose} does not {VERB_OF[stage]} {', '.join(lacking)} (it {VERB_OF[stage]}s {', '.join(listed)})"


# The fix is one of the row's own that takes them all: run for the agent once it names nothing, or, where
# its org has no key for it, said with the reason and the command that brings one.
def _say_fix(stage: Stage, languages: Sequence[str], catalog: Catalog, keys: providers.Keyring) -> str:
    what = "transcriber" if stage is Stage.stt else "voice"
    suited = providers.list_suited(stage, languages, catalog, keys)
    runs = next((one for one in suited if one.refused is None), None)
    if runs is not None:
        return f"take the {what} out of its settings and Pinecall runs {runs.vendor}/{runs.model}"
    if suited:
        first = suited[0]
        return (
            f"{first.vendor}/{first.model} does, and this org cannot run it ({first.refused}): "
            f"pinecall providers add {first.vendor}"
        )
    return f"no {what} this runtime lists does: name one that does"
