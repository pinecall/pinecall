"""A declaration resolved into stages: each on the vendor it names or the row's default, on its key, as tuned."""

import dataclasses
import logging
from collections.abc import Iterable, Sequence
from typing import Protocol

from runtime.enums import Stage
from runtime.exceptions import Conflict, Forbidden, ServiceUnavailable, ValidationError
from runtime.providers.catalog import Catalog
from runtime.providers.service.catalog import stage_options_of
from runtime.providers.service.keyring import Keyring, running_on
from runtime.providers.stage import TURN_MODEL_OF, Credentials, Model, Pipeline, Running, Voice, primary_language
from runtime.wire.parts import EndOfTurn

logger = logging.getLogger(__name__)


# An agent's declaration is `agents`', above this domain. What resolving its stages reads of it is
# this much, and whatever carries it is handed in.
class AgentStages(Protocol):
    """What a resolved declaration says of an agent's stages: the vendors it names, its language, who takes over."""

    @property
    def language(self) -> str | None:
        """The language its calls are in."""
        ...

    @property
    def llm(self) -> Model | None:
        """The model it thinks with, where it names one."""
        ...

    @property
    def stt(self) -> Model | None:
        """The ears it hears with, where it names them."""
        ...

    @property
    def voice(self) -> Voice | None:
        """The voice it speaks with, where it names one."""
        ...

    @property
    def judge(self) -> Model | None:
        """The model its calls are judged on, where it names one."""
        ...

    @property
    def realtime(self) -> Model | None:
        """The model a voice call of its runs on alone, hearing and speaking itself."""
        ...

    @property
    def stt_fallbacks(self) -> Sequence[Model]:
        """The ears that take over, in order: over the row's own."""
        ...

    @property
    def tts_fallbacks(self) -> Sequence[Model]:
        """The voices that take over, in order: over the row's own."""
        ...


def build_pipeline(declaration: AgentStages, catalog: Catalog, keys: Keyring) -> Pipeline:
    """The stages an agent runs: its vendors or the defaults, each with its key and options."""
    language = primary_language(declaration.language)
    llm = thinking_of(declaration, catalog, keys)
    stt = _back_by(
        stage_on_its_key(Stage.stt, declaration.stt, catalog, keys), Stage.stt, declaration.stt_fallbacks, catalog, keys
    )
    tts = _back_by(
        stage_on_its_key(Stage.tts, declaration.voice, catalog, keys),
        Stage.tts,
        declaration.tts_fallbacks,
        catalog,
        keys,
    )
    heard = dict.fromkeys(item for item in (language, *catalog.hints) if item)
    voice = declaration.voice.voice_id if declaration.voice else None
    ears = [dataclasses.replace(item, language=language, hints=tuple(heard)) for item in (stt, *stt.fallbacks)]
    # The agent's voice is its vendor's; a vendor that takes over speaks the row's for the language.
    voices = [
        dataclasses.replace(
            item, language=language, voice=(voice if item is tts else None) or catalog.voice_for(item.vendor, language)
        )
        for item in (tts, *tts.fallbacks)
    ]
    realtime = None if declaration.realtime is None else talking_of(declaration.realtime, keys)
    return Pipeline(llm=llm, stt=ears[0].over(*ears[1:]), tts=voices[0].over(*voices[1:]), realtime=realtime)


# A realtime model runs on the org's own key alone, as a plugin's own class does, and is told the
# agent's options alone: the row's options for the vendor are its LLM's.
def talking_of(named: Model, keys: Keyring) -> Running:
    """The realtime model a voice call runs on, on the org's own key."""
    chosen = running_on(keys, named.vendor, named.model or None)
    if chosen.lent:
        raise Conflict(
            f"a realtime model runs on the org's own {chosen.vendor} key, and this agent's would run on the "
            f"platform's: add yours with pinecall providers add {chosen.vendor}"
        )
    return dataclasses.replace(chosen, options=dict(named.options))


# A written call runs this stage alone: a call with no voice is not refused for want of one.
def thinking_of(declaration: AgentStages, catalog: Catalog, keys: Keyring) -> Running:
    """The model an agent thinks with, on its key, at the temperature it declared."""
    llm = stage_on_its_key(Stage.llm, declaration.llm, catalog, keys)
    if declaration.llm is None or declaration.llm.temperature is None:
        return llm
    return dataclasses.replace(llm, options={**llm.options, "temperature": declaration.llm.temperature})


# An agent that names its vendor runs it alone; one on the row's default runs the default's
# fallbacks behind it, each on its own key, in the row's order. A fallback this org cannot key is
# left out.
def stage_on_its_key(stage: Stage, named: Model | Voice | None, catalog: Catalog, keys: Keyring) -> Running:
    """One stage on its key: the vendor named or the default, with the operator's options."""
    if named is not None:
        chosen = _run_on_its_key(stage, named.vendor, named.model or None, catalog, keys)
        return _run_as_named(stage, chosen, named)
    default = catalog.defaults[stage]
    chosen = _run_on_its_key(stage, default.vendor, default.model, catalog, keys)
    return chosen.over(*_list_with_a_key(stage, ((one.vendor, one.model) for one in default.fallbacks), catalog, keys))


def vendor_on(stage: Stage, vendor: str, credentials: Credentials, catalog: Catalog) -> Running:
    """The vendor's stage on these credentials, with the row's model and options for it: as a call runs it."""
    return _run_on_its_key(stage, vendor, None, catalog, Keyring(own={vendor: credentials}))


# Checked where an agent declares itself and where its settings are set, not first on a call.
# Every stage the agent names is tried on its key here, when it is declared: a vendor nobody keyed is
# refused at agent.configure in the sentence a call would have closed with, never on the first call.
def refuse_what_cannot_run(declaration: AgentStages, catalog: Catalog, keys: Keyring) -> None:
    """Refuse a stage with no key, its own plugin or a realtime model on a lent key, or an end of turn it lacks."""
    stages: tuple[tuple[Stage, Model | Voice | None], ...] = (
        (Stage.llm, declaration.llm),
        (Stage.stt, declaration.stt),
        (Stage.tts, declaration.voice),
        (Stage.llm, declaration.judge),
    )
    for stage, named in stages:
        if named is not None:
            stage_on_its_key(stage, named, catalog, keys)
    if declaration.realtime is not None:
        talking_of(declaration.realtime, keys)


# ── private ──


# What an agent names of the plugin wins over the operator's options for the vendor: its class,
# and each keyword argument it names, on the org's own key alone; and who ends the turn.
def _run_as_named(stage: Stage, chosen: Running, named: Model | Voice) -> Running:
    if named.builds is not None or named.options:
        if chosen.lent:
            raise Conflict(
                f"{stage} options and builds run on the org's own {chosen.vendor} key, and this agent's "
                f"{stage} would run on the platform's: add yours with pinecall providers add {chosen.vendor}, "
                "or take them out"
            )
        chosen = dataclasses.replace(
            chosen, builds=named.builds or chosen.builds, options={**chosen.options, **named.options}
        )
    if isinstance(named, Model) and named.end_of_turn is not None:
        return _end_turns_by(chosen, named.end_of_turn)
    return chosen


# The ears end the turn only where the operator's row says this vendor's class does (Flux).
def _end_turns_by(chosen: Running, end_of_turn: EndOfTurn) -> Running:
    if end_of_turn == "stt":
        if not chosen.ends_the_turn:
            raise ValidationError(
                f"{chosen.vendor} does not end the turn itself here: end of turn livekit or smart-turn reads it "
                "off the audio instead"
            )
        return chosen
    return dataclasses.replace(chosen, ends_the_turn=False, turn_model=TURN_MODEL_OF[end_of_turn])


# A vendor named with no model runs the row's model for it, else the platform default's where the
# default is that vendor: never the plugin's own, which Google retires under new users without notice.
def _run_on_its_key(stage: Stage, vendor: str, named: str | None, catalog: Catalog, keys: Keyring) -> Running:
    model = named or catalog.model_for(stage, vendor)
    chosen = running_on(keys, vendor, model)
    options = stage_options_of(catalog, stage, vendor, model)
    if options is None:
        return chosen
    return dataclasses.replace(
        chosen,
        builds=options.builds,
        options=dict(options.options),
        ends_the_turn=options.ends_the_turn,
        commits_when_told=options.commits_when_told,
        turn_model=options.turn_model or chosen.turn_model,
        request=dict(options.request),
    )


def _list_with_a_key(
    stage: Stage, named: Iterable[tuple[str, str | None]], catalog: Catalog, keys: Keyring
) -> list[Running]:
    backups: list[Running] = []
    for vendor, model in named:
        try:
            backups.append(_run_on_its_key(stage, vendor, model, catalog, keys))
        except (ServiceUnavailable, Forbidden):
            logger.info("%s fallback %s has no key this org may run it on", stage, vendor)
    return backups


# The agent's own fallbacks take the place of the ones its stage came with; none leaves those.
def _back_by(chosen: Running, stage: Stage, named: Sequence[Model], catalog: Catalog, keys: Keyring) -> Running:
    if not named:
        return chosen
    return chosen.over(*_list_with_a_key(stage, ((one.vendor, one.model or None) for one in named), catalog, keys))
