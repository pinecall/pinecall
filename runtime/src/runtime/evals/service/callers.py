"""The simulated caller: the model of its lines and the voice that speaks them, each on a key of the org's."""

import dataclasses
import logging
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.agents.declaration import Declaration
from runtime.enums import Stage
from runtime.exceptions import PinecallError, UpstreamError
from runtime.judging import service as judging
from runtime.kit.crypto import Vault
from runtime.kit.text import JsonObject
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.providers.stage import Model, Running, Voice, primary_language
from runtime.wire.base import Entry
from runtime.wire.metrics import LLMModelUsage, ModelUsage

logger = logging.getLogger(__name__)

# As LiveKit's simulations frame it: the persona is the system message, its facts a block in it.
A_CALLER = (
    "You are a person who has just phoned a business, and you answer as that person and nobody "
    "else. Say one short turn, the way somebody speaks on the phone: no narration, no stage "
    "directions, no quotation marks, never more than two sentences. Speak the language the "
    "business is speaking to you unless your own style says otherwise. Use the facts about "
    "yourself when they are asked for, and volunteer one when it moves you towards what you "
    "want. Never invent a fact about yourself that is not listed. Hang up once you have what you "
    "came for, or once it is clear you will not get it."
)
PERSONA = "What you want: {goal}\nHow you talk: {style}\nFacts about you:\n{facts}"
NO_FACTS = "  (you were given none: do not make any up)"
# The last turn is announced, so the caller says goodbye instead of being cut mid-sentence.
TURNS_LEFT = "You have {left} turn(s) left in this call."
THE_LAST_TURN = "This is your last turn: finish what you are saying and hang up."
# Asked once more, its words in front of it, as a judge is: a small model now and then answers in words.
ONLY_THE_LINE = "Answer by calling say_next_line, and nothing else."
SAID_AT_MOST = 200
THE_CALLERS_LINE = "the caller's next line"

# The line is read off the call's arguments; the tool itself never runs.
SAY_NEXT_LINE: JsonObject = {
    "name": "say_next_line",
    "description": "Say your next turn on the phone.",
    "parameters": {
        "type": "object",
        "properties": {
            "line": {"type": "string", "description": "What you say out loud, in one or two sentences."},
            "hanging_up": {
                "type": "boolean",
                "description": "True when this is the last thing you will say on this call.",
            },
        },
        "required": ["line", "hanging_up"],
    },
}

type Side = Literal["agent", "caller"]
SIDES: Mapping[str, Side] = {"turn.agent": "agent", "turn.user": "caller"}


@dataclass(frozen=True, slots=True)
class Heard:
    """One side's turn of a call, as the caller heard it."""

    who: Side
    said: str


@dataclass(frozen=True, slots=True)
class Improvised:
    """The caller's next line, whether it hangs up with it, and what its model was paid for it."""

    say: str
    hangup: bool
    usage: LLMModelUsage | None = None


# The box pays a simulated caller's model and voice: one call spends up to the providers row's
# `caller.ceiling_usd`, the line that crosses it the last one said. Priced as a call is.
@dataclass
class Spending:
    """What one simulated call's caller has spent, line by line, against its ceiling."""

    catalog: Catalog
    used: list[ModelUsage] = field(default_factory=list[ModelUsage])

    @property
    def usd(self) -> float:
        """What the caller's lines and voice have cost so far, by the box's rates."""
        return providers.cost_of(self.used, self.catalog).usd

    @property
    def is_over(self) -> bool:
        """Whether the call has spent its ceiling; never, where the row names none."""
        caller = self.catalog.caller
        return caller is not None and self.usd >= caller.ceiling_usd

    # A line's model is counted as it is improvised, its voice as it is said: what saying it cost is
    # the line's to answer (`Line.say`), and a written line answers nothing.
    def count(self, used: ModelUsage | None) -> None:
        """One more thing the caller used: the model of a line, or the voice that said it."""
        if used is not None:
            self.used.append(used)


@dataclass(frozen=True, slots=True)
class CallerModel:
    """The model a caller's lines are improvised on, and its `vendor/model` as it runs."""

    model: providers.Answerer
    named: str


@dataclass(frozen=True, slots=True)
class Caller:
    """Who plays a simulated call: the persona, the model of its lines, and what it has spent."""

    persona: judging.Persona
    model: providers.Answerer
    spending: Spending


def list_heard(entries: Sequence[Entry]) -> list[Heard]:
    """Both sides' turns of a call's log, in order, as the caller heard them."""
    return [Heard(SIDES[entry.type], str(entry.data.get("text", ""))) for entry in entries if entry.type in SIDES]


# What the caller expects of the agent is the judge's alone: a caller that knew it would play to it.
# The request is the providers': the tool forced, the model asked once more with its words in front
# of it, the vendor's no said in our words. Until 2026-11 it was written here a second time.
async def improvise_line(
    model: providers.Answerer, persona: judging.Persona, heard: Sequence[Heard], turns_left: int
) -> Improvised:
    """The caller's next turn: the persona, the call so far, and how many turns are left."""
    answer = await model.ask_by_tool(
        _call_so_far(persona, heard, turns_left),
        SAY_NEXT_LINE,
        insist=ONLY_THE_LINE,
        what=THE_CALLERS_LINE,
        patience=judging.ASKED_WITHIN,
    )
    if answer.arguments is None:
        raise UpstreamError(
            "the model playing the caller answered without calling say_next_line: it said "
            f"{answer.text.strip()[:SAID_AT_MOST]!r}"
        )
    line = str(answer.arguments.get("line", "")).strip()
    # An empty line is a caller who has hung up.
    return Improvised(say=line, hangup=bool(answer.arguments.get("hanging_up", False)) or not line, usage=answer.usage)


def name_of(stage: Running) -> str:
    """A stage as it runs, `vendor/model`, or the vendor alone on its plugin's own model."""
    return stage.vendor if not stage.model else f"{stage.vendor}/{stage.model}"


# The persona's model, else the box's caller's, on the key the org may run it on: refused as a
# call of the org's is, for want of a key, before anything is built.
def caller_stage(catalog: Catalog, keys: providers.Keyring, persona: judging.Persona) -> Running:
    """The stage that improvises the caller's lines."""
    row = None if catalog.caller is None else catalog.caller.llm
    named = agents.name_model(persona.llm or None, Stage.llm, in_use=catalog.default_vendors[Stage.llm]) or (
        None if row is None else Model(vendor=row.vendor, model=row.model or "")
    )
    return providers.stage_on_its_key(Stage.llm, named, catalog, keys)


# `tts` names a vendor, never a model: the persona's, else the one in use.
def voice_vendor(catalog: Catalog, persona: judging.Persona | None) -> tuple[str, str | None]:
    """The vendor and the model the caller's voice is of."""
    in_use = catalog.default_vendors[Stage.tts]
    chosen = None if persona is None else agents.name_model(persona.tts or None, Stage.tts, in_use=in_use)
    return (in_use, None) if chosen is None else (chosen.vendor, chosen.model or None)


# Read in a transaction of its own: the model is held for a whole call, and no connection is.
@asynccontextmanager
async def open_caller_model(
    sessions: async_sessionmaker[AsyncSession], vault: Vault, scope: Scope, persona: judging.Persona
) -> AsyncGenerator[CallerModel]:
    """The model that improvises the caller's lines: the persona's, else the box's caller's."""
    async with sessions.begin() as session:
        catalog = await providers.get_catalog(session)
        keys = await providers.keys_of(session, vault, scope)
    stage = caller_stage(catalog, keys, persona)
    async with providers.open_answerer(stage) as model:
        yield CallerModel(model, name_of(stage))


# The caller speaks in the agent's language and never in the agent's own voice. `agent` is the agent
# as a call of the scope runs it (its declaration over the settings); None for one no app of the org holds.
async def caller_voice(
    session: AsyncSession, vault: Vault, scope: Scope, agent: Declaration | None, persona: judging.Persona | None
) -> Running:
    """The caller's voice: the persona's, else one of the vendor's that is not the agent's."""
    catalog = await providers.get_catalog(session)
    vendor, model = voice_vendor(catalog, persona)
    keys = await providers.keys_of(session, vault, scope)
    language = None if agent is None else agent.language
    agents_voice = _voice_the_agent_speaks(agent, catalog, keys, vendor)
    chosen = pick_caller_voice(
        catalog.voices, vendor, agents_voice, language, None if persona is None else persona.voice
    )
    unnamed = providers.stage_on_its_key(Stage.tts, Voice(vendor=vendor, model=model), catalog, keys)
    if chosen is None:
        chosen = await _find_another_listed(catalog, unnamed, agents_voice, language)
    stage = providers.stage_on_its_key(Stage.tts, Voice(vendor=vendor, model=model, voice_id=chosen), catalog, keys)
    return dataclasses.replace(stage, voice=chosen, language=language)


# The operator's voices per language are the ones an agent speaks with when it names none; the
# caller takes the persona's own unless it is the agent's, else one the agent is not using, in its
# language, else in English, else the plugin's.
def pick_caller_voice(
    voices: Mapping[str, str], vendor: str, agents_voice: str | None, language: str | None, wanted: str | None = None
) -> str | None:
    """The voice the caller speaks with: the persona's when it has one, never the agent's."""
    own = f"{vendor}/{primary_language(language) or 'en'}"
    ordered = [wanted, voices.get(own), voices.get(f"{vendor}/en")]
    ordered += [voice for key, voice in voices.items() if key.startswith(f"{vendor}/")]
    return next((voice for voice in ordered if voice and voice != agents_voice), None)


# The model is the caller: its turns are the assistant's, the business's are the user's.
def _call_so_far(persona: judging.Persona, heard: Sequence[Heard], turns_left: int) -> list[providers.Line]:
    lines = [providers.Line("system", f"{A_CALLER}\n\n{_persona_of(persona)}")]
    lines += [providers.Line("user" if turn.who == "agent" else "assistant", turn.said) for turn in heard]
    lines.append(providers.Line("system", THE_LAST_TURN if turns_left <= 1 else TURNS_LEFT.format(left=turns_left)))
    return lines


def _persona_of(persona: judging.Persona) -> str:
    facts = "\n".join(f"  {name}: {value}" for name, value in persona.facts.items())
    return PERSONA.format(goal=persona.goal, style=persona.style, facts=facts or NO_FACTS)


# The voice the agent speaks with on the caller's vendor: the one it declared, else the operator's
# for its language, else its plugin's own default, which is what its pipeline gives it; on another
# vendor no voice of the caller's can be the agent's.
def _voice_the_agent_speaks(
    agent: Declaration | None, catalog: Catalog, keys: providers.Keyring, vendor: str
) -> str | None:
    asked_for = (None if agent is None else agent.voice) or Voice(vendor=catalog.default_vendors[Stage.tts])
    if asked_for.vendor != vendor:
        return None
    row = catalog.voices.get(f"{vendor}/{primary_language(None if agent is None else agent.language)}")
    if asked_for.voice_id or row:
        return asked_for.voice_id or row
    return providers.default_voice(providers.stage_on_its_key(Stage.tts, asked_for, catalog, keys))


# The operator gave no voice the agent is not speaking in: the vendor's own, the row's listing
# first, in the agent's language before any other. A vendor that lists none leaves the plugin's.
async def _find_another_listed(
    catalog: Catalog, unnamed: Running, agents_voice: str | None, language: str | None
) -> str | None:
    spoken_in = primary_language(language)
    try:
        listed = providers.list_in_catalog(catalog, unnamed.vendor, spoken_in) or await providers.list_by_vendor(
            dataclasses.replace(unnamed, language=spoken_in)
        )
    except PinecallError:
        # A vendor that would not list its voices: the caller speaks in its plugin's own, the agent's too.
        logger.warning(
            "%s listed no voice for a simulated caller to speak in: it speaks in the plugin's own",
            unnamed.vendor,
            exc_info=True,
        )
        return None
    others = [voice for voice in listed if voice.id != agents_voice]
    same_language = [voice for voice in others if _speaks(voice.detail, spoken_in)]
    found = (same_language or others)[:1]
    return found[0].id if found else None


def _speaks(detail: Mapping[str, object], language: str | None) -> bool:
    its_own = str(detail.get("language") or "")
    return language is None or its_own == "" or its_own.startswith(language)
