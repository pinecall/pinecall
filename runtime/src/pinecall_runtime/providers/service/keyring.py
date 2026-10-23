"""Whose key each stage of a call runs on: the org's own runs anything, the box's what it lends."""

import dataclasses
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import AgentConfig, Modality, Model, Voice
from pinecall_runtime.billing import service as billing
from pinecall_runtime.exceptions import Conflict, Forbidden, ServiceUnavailable, ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.providers.schemas import (
    Availability,
    Catalog,
    Catalogue,
    ProviderRow,
    Standing,
)
from pinecall_runtime.providers.service import plugins
from pinecall_runtime.providers.service.catalog import tuning_of
from pinecall_runtime.providers.service.held import box_credentials, own_credentials
from pinecall_runtime.providers.service.plugins import (
    Credentials,
    Running,
    Vendor,
    primary_language,
)
from pinecall_runtime.providers.service.stages import takes_a_key
from pinecall_runtime.wire.parts import EndOfTurn

logger = logging.getLogger(__name__)

# Model ids carry slashes of their own (`openai/gpt-5` on LiveKit Inference): the first ends the vendor.
SEPARATOR = "/"
# What a dated snapshot adds to a model's name: `-20251001`, `-2025-08-07`, `@20240229`.
A_SNAPSHOT = re.compile(r"[-@](\d{8}|\d{4}-\d{2}-\d{2})")
# Availabilities a call can run on.
READY = frozenset({"yours", "offered"})
# v1's word for each, which the console draws: a vendor nobody keyed for this org has "no key".
STANDING: dict[Availability, Standing] = {
    "yours": "ready",
    "offered": "ready",
    "bring your own": "no key",
    "broken": "no plugin",
}


@dataclass(frozen=True, slots=True)
class Keyring:
    """What a call may run on: the org's own credentials, the box's, and what the box lends it."""

    own: Mapping[str, Credentials] = field(default_factory=dict[str, Credentials])
    box: Mapping[str, Credentials] = field(default_factory=dict[str, Credentials])
    # quotas.lends: None lends everything the box holds, empty lends nothing.
    lends: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class Pipeline:
    """The three stages of a voice call, each on the key it runs on."""

    llm: Running
    stt: Running
    tts: Running
    # The model a voice call runs on alone, hearing and speaking itself, where the agent names one.
    realtime: Running | None = None

    # The gateway keeps these with the call's facts: their usage is the operator's to bill.
    @property
    def lent(self) -> list[str]:
        """The vendors the call may run on the box's key, in stage order, once each."""
        each = (item for stage in (self.llm, self.stt, self.tts) for item in (stage, *stage.fallbacks))
        return list(dict.fromkeys(item.vendor for item in each if item.lent))

    # The row's order stands but for the vendors `failing` names (over their error line now),
    # which go last, among themselves in the row's order too.
    def demoting(self, failing: frozenset[str]) -> "Pipeline":
        """The same stages, each with the vendors failing now behind the ones that are not."""
        return Pipeline(
            llm=_behind(self.llm, failing),
            stt=_behind(self.stt, failing),
            tts=_behind(self.tts, failing),
            realtime=self.realtime,
        )


@dataclass(frozen=True, slots=True)
class Readiness:
    """One vendor as `GET /v1/providers` shows it to an org: what it does, and whose key runs it."""

    name: str
    does: tuple[Modality, ...]
    availability: Availability
    broken: str | None = None


# ── the keys themselves ──


# Read per call, so a rotated key runs from the next call on.
async def keys_of(session: AsyncSession, vault: Vault, scope: Scope) -> Keyring:
    """What the org's calls in the env may run on."""
    quotas = await billing.get_quotas(session, scope.org, scope.env)
    return Keyring(
        own=await own_credentials(session, vault, scope.org),
        box=await box_credentials(session, vault),
        lends=quotas.lends,
    )


# ── a stage on its key ──


def build_pipeline(config: AgentConfig, catalog: Catalog, keys: Keyring) -> Pipeline:
    """The stages an agent runs: its vendors or the defaults, each with its key and options."""
    language = primary_language(config.language)
    llm = thinking_of(config, catalog, keys)
    stt = stage_on_its_key("stt", config.stt, catalog, keys)
    tts = stage_on_its_key("tts", config.voice, catalog, keys)
    heard = dict.fromkeys(item for item in (language, *catalog.hints) if item)
    voice = config.voice.voice_id if config.voice else None
    ears = (dataclasses.replace(item, language=language, hints=tuple(heard)) for item in (stt, *stt.fallbacks))
    # The agent's voice is its vendor's; a vendor that takes over speaks the row's for the language.
    voices = (
        dataclasses.replace(
            item,
            language=language,
            voice=(voice if item is tts else None) or catalog.voices.get(f"{item.vendor}{SEPARATOR}{language}"),
        )
        for item in (tts, *tts.fallbacks)
    )
    realtime = None if config.realtime is None else talking_of(config.realtime, keys)
    return Pipeline(llm=llm, stt=_over(*ears), tts=_over(*voices), realtime=realtime)


# A realtime model runs on the org's own key alone, as a plugin's own class does, and is told the
# agent's options alone: the row's options for the vendor are its LLM's.
def talking_of(declared: Model, keys: Keyring) -> Running:
    """The realtime model a voice call runs on, on the org's own key."""
    chosen = running_on(keys, declared.provider, declared.model or None)
    if chosen.lent:
        raise Conflict(
            f"a realtime model runs on the org's own {chosen.vendor} key, and this agent's would run on the "
            f"platform's: add yours with pinecall providers add {chosen.vendor}"
        )
    return dataclasses.replace(chosen, options=dict(declared.options))


# A written call runs this stage alone: a call with no voice is not refused for want of one.
def thinking_of(config: AgentConfig, catalog: Catalog, keys: Keyring) -> Running:
    """The model an agent thinks with, on its key, at the temperature it declared."""
    llm = stage_on_its_key("llm", config.llm, catalog, keys)
    if config.llm is None or config.llm.temperature is None:
        return llm
    return dataclasses.replace(llm, options={**llm.options, "temperature": config.llm.temperature})


# An agent that names its vendor runs it alone; one on the row's default runs the default's
# fallbacks behind it, each on its own key, in the row's order. A fallback this org cannot key is
# left out.
def stage_on_its_key(modality: Modality, declared: Model | Voice | None, catalog: Catalog, keys: Keyring) -> Running:
    """One stage on its key: the vendor declared or the default, with the operator's options."""
    if declared is not None:
        chosen = _on_its_key(modality, declared.provider, declared.model or None, catalog, keys)
        return _as_declared(modality, chosen, declared)
    default = catalog.defaults[modality]
    chosen = _on_its_key(modality, default.vendor, default.model, catalog, keys)
    backups: list[Running] = []
    for fallback in default.fallbacks:
        try:
            backups.append(_on_its_key(modality, fallback.vendor, fallback.model, catalog, keys))
        except (ServiceUnavailable, Forbidden):
            logger.info("%s fallback %s has no key this org may run it on", modality, fallback.vendor)
    return _over(chosen, *backups)


def vendor_on(modality: Modality, vendor: str, credentials: Credentials, catalog: Catalog) -> Running:
    """The vendor's stage on these credentials, with the row's model and options for it: as a call runs it."""
    return _on_its_key(modality, vendor, None, catalog, Keyring(own={vendor: credentials}))


def running_on(keys: Keyring, vendor: str, model: str | None) -> Running:
    """The vendor on the org's own key, else on a key the box lends; refused before the call."""
    own = keys.own.get(vendor)
    if own is not None:
        return Running(vendor=vendor, credentials=own, model=model)
    box = keys.box.get(vendor)
    if box is None:
        if not takes_a_key(vendor):
            return Running(vendor=vendor, credentials="", model=model)
        raise ServiceUnavailable(f"{vendor} has no key: the org brought none and the box holds none")
    if not is_lent(keys.lends, vendor, model):
        raise Forbidden(lending_refusal(keys.lends or frozenset(), vendor, model))
    return Running(vendor=vendor, credentials=box, model=model, lent=True)


# A model entry lends itself and its dated snapshots (`anthropic/claude-haiku-5-5` lends
# `claude-haiku-5-5-20261001`), never a sibling that only starts the same (`openai/gpt-5` lends no
# `gpt-5-pro`); a plugin's own default needs the whole vendor.
def is_lent(lends: frozenset[str] | None, vendor: str, model: str | None) -> bool:
    """Whether the box lends this org its key for this vendor and model."""
    if lends is None or vendor in lends:
        return True
    if model is None:
        return False
    prefix = f"{vendor}{SEPARATOR}"
    named = (entry.removeprefix(prefix) for entry in lends if entry.startswith(prefix))
    return any(model == entry or _a_snapshot_of(entry, model) for entry in named)


def lending_refusal(lends: frozenset[str], vendor: str, model: str | None) -> str:
    """The sentence a refused org reads: what it asked, what it may run, and the other way."""
    asked = vendor if model is None else f"{vendor}{SEPARATOR}{model}"
    may = ", ".join(sorted(lends)) if lends else "nothing of the box's"
    return f"{asked} is not lent to this org: it may run on {may}, or on a key of its own"


def parse_lending(entries: Iterable[str]) -> frozenset[str]:
    """The entries an operator lends, each a vendor installed here or `vendor/model`."""
    parsed: set[str] = set()
    for entry in entries:
        named, slash, model = entry.strip().partition(SEPARATOR)
        vendor = named.lower()
        if not plugins.is_installed(vendor):
            raise ValidationError(f"{entry!r} lends no vendor installed here")
        if slash and not model:
            raise ValidationError(f"{entry!r} names a vendor and no model after the slash")
        parsed.add(f"{vendor}{SEPARATOR}{model}" if slash else vendor)
    return frozenset(parsed)


# Checked where an agent declares itself and where its settings are set, not first on a call.
# Every stage the agent names is tried on its key here, when it is declared: a vendor nobody keyed is
# refused at agent.configure in the sentence a call would have closed with, never on the first call.
def refuse_what_cannot_run(config: AgentConfig, catalog: Catalog, keys: Keyring) -> None:
    """Refuse a stage with no key, its own plugin or a realtime model on a lent key, or an end of turn it lacks."""
    stages: tuple[tuple[Modality, Model | Voice | None], ...] = (
        ("llm", config.llm),
        ("stt", config.stt),
        ("tts", config.voice),
        ("llm", config.judge),
    )
    for modality, declared in stages:
        if declared is not None:
            stage_on_its_key(modality, declared, catalog, keys)
    if config.realtime is not None:
        talking_of(config.realtime, keys)


# ── the catalogue an org reads ──


def readiness(vendors: Mapping[str, Vendor], keys: Keyring) -> list[Readiness]:
    """Every installed vendor, sorted, and how this org may run it."""
    return [
        Readiness(name=v.name, does=tuple(sorted(v.does)), availability=_availability_of(v, keys), broken=v.broken)
        for v in sorted(vendors.values(), key=lambda one: one.name)
    ]


def catalogue_of(catalog: Catalog, keys: Keyring) -> Catalogue:
    """Every installed vendor as this org may run it, with the row's defaults and models."""
    return Catalogue(
        providers=[
            ProviderRow(
                name=vendor.name,
                does=list(vendor.does),
                aliases=[],
                note=vendor.broken or "",
                standing=STANDING[vendor.availability],
                ready=vendor.availability in READY,
                env=None,
                extra=vendor.name,
                voices_listed=lists_voices(vendor.name, vendor.does) or _lists_any(catalog, vendor.name),
                availability=vendor.availability,
                broken=vendor.broken,
            )
            for vendor in readiness(plugins.installed(), keys)
        ],
        defaults=catalog.default_vendors,
        voices=[],
        models=_models_offered(catalog, keys),
        runs=runs_of(catalog, plugins.installed()),
        realtime={vendor.name: list(vendor.realtime) for vendor in plugins.installed().values() if vendor.realtime},
    )


# The model a call on a vendor runs when none is picked: the row's, else the one the plugin builds
# where its constructor says one.
def runs_of(catalog: Catalog, installed: Mapping[str, Vendor]) -> dict[str, str]:
    """By `stage/vendor`, the model that runs when none is picked, where it is known."""
    runs = {
        f"{stage}{SEPARATOR}{vendor.name}": model
        for vendor in installed.values()
        for stage, model in vendor.defaults.items()
    }
    runs.update(catalog.models)
    return runs


# What a picker offers this org of each vendor and stage: the one that runs first, then the models the
# row offers, kept to what the box lends the org where it lends by model (an entry names no stage, so
# a model the row does not list is offered nowhere). On the org's own key, every one.
def _models_offered(catalog: Catalog, keys: Keyring) -> dict[str, list[str]]:
    offered: dict[str, list[str]] = {}
    runs = runs_of(catalog, plugins.installed())
    for named in sorted({*catalog.models, *catalog.offered}):
        vendor = named.partition(SEPARATOR)[2]
        first = [runs[named]] if named in runs else []
        listed = list(dict.fromkeys([*first, *catalog.offered.get(named, ())]))
        if vendor not in keys.own and keys.lends is not None and vendor not in keys.lends:
            listed = [model for model in listed if is_lent(keys.lends, vendor, model)]
        if listed:
            offered[named] = listed
    return offered


# A plugin lists its voices when its TTS class has a `list_voices`; nothing is built to ask.
def lists_voices(vendor: str, does: tuple[Modality, ...]) -> bool:
    """Whether the vendor's plugin can list its voices."""
    if "tts" not in does:
        return False
    try:
        speech = getattr(plugins.plugin(vendor), "TTS", None)
    except (ValidationError, ServiceUnavailable):
        return False
    return callable(getattr(speech, "list_voices", None))


# ── private ──


# What an agent names of the plugin wins over the operator's options for the vendor: its class,
# and each keyword argument it names, on the org's own key alone; and who ends the turn.
def _as_declared(modality: Modality, chosen: Running, declared: Model | Voice) -> Running:
    if declared.builds is not None or declared.options:
        if chosen.lent:
            raise Conflict(
                f"{modality} options and builds run on the org's own {chosen.vendor} key, and this agent's "
                f"{modality} would run on the platform's: add yours with pinecall providers add {chosen.vendor}, "
                "or take them out"
            )
        chosen = dataclasses.replace(
            chosen, builds=declared.builds or chosen.builds, options={**chosen.options, **declared.options}
        )
    if isinstance(declared, Model) and declared.end_of_turn is not None:
        return _ended_by(chosen, declared.end_of_turn)
    return chosen


# The ears end the turn only where the operator's row says this vendor's class does (Flux).
def _ended_by(chosen: Running, end_of_turn: EndOfTurn) -> Running:
    if end_of_turn == "stt":
        if not chosen.ends_the_turn:
            raise ValidationError(
                f"{chosen.vendor} does not end the turn itself here: end of turn livekit or smart-turn reads it "
                "off the audio instead"
            )
        return chosen
    return dataclasses.replace(
        chosen, ends_the_turn=False, turn_model="smart-turn-v3" if end_of_turn == "smart-turn" else "v1-mini"
    )


def _a_snapshot_of(entry: str, model: str) -> bool:
    return model.startswith(entry) and A_SNAPSHOT.fullmatch(model[len(entry) :]) is not None


def _on_its_key(modality: Modality, vendor: str, named: str | None, catalog: Catalog, keys: Keyring) -> Running:
    model = named or catalog.models.get(f"{modality}{SEPARATOR}{vendor}")
    chosen = running_on(keys, vendor, model)
    options = tuning_of(catalog, modality, vendor, model)
    if options is None:
        return chosen
    return dataclasses.replace(
        chosen,
        builds=options.builds,
        options=dict(options.options),
        ends_the_turn=options.ends_the_turn,
        turn_model=options.turn_model or chosen.turn_model,
        request=dict(options.request),
    )


def _over(primary: Running, *fallbacks: Running) -> Running:
    return dataclasses.replace(primary, fallbacks=fallbacks)


def _behind(chosen: Running, failing: frozenset[str]) -> Running:
    chain = (dataclasses.replace(chosen, fallbacks=()), *chosen.fallbacks)
    return _over(*sorted(chain, key=lambda item: item.vendor in failing))


def _availability_of(vendor: Vendor, keys: Keyring) -> Availability:
    if vendor.broken is not None:
        return "broken"
    if vendor.name in keys.own:
        return "yours"
    if vendor.name in keys.box and _lends_any_of(keys.lends, vendor.name):
        return "offered"
    return "bring your own"


# A vendor lent whole, or by any one of its models: the picker lists those.
def _lends_any_of(lends: frozenset[str] | None, vendor: str) -> bool:
    return is_lent(lends, vendor, None) or any(entry.startswith(f"{vendor}{SEPARATOR}") for entry in lends or ())


def _lists_any(catalog: Catalog, vendor: str) -> bool:
    return any(key.partition("/")[0] == vendor for key in catalog.listed)
