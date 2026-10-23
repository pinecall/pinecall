"""Who plays a simulated caller: the model of its lines and the voice that speaks them, each on a key of the org's."""

import dataclasses
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Never

from livekit.agents import llm
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import AgentConfig, Model, Voice
from pinecall_runtime.agents.service import settings, tuning
from pinecall_runtime.calls import service as calls
from pinecall_runtime.evals.service import spoken
from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.providers import service as providers

logger = logging.getLogger(__name__)

# A vendor that would not list its voices: the caller speaks in its plugin's own, the agent's too.
NONE_LISTED = "%s listed no voice for a simulated caller to speak in: it speaks in the plugin's own"


@dataclass(frozen=True, slots=True)
class CallerModel:
    """The model a caller's lines are improvised on, and its `vendor/model` as it runs."""

    llm: llm.LLM[Never]
    named: str


def named(stage: providers.Running) -> str:
    """A stage as it runs, `vendor/model`, or the vendor alone on its plugin's own model."""
    return stage.vendor if not stage.model else f"{stage.vendor}/{stage.model}"


# The persona's model, else the box's caller's, on the key the org may run it on: refused as a
# call of the org's is, for want of a key, before anything is built.
def caller_stage(
    configured: providers.Catalog, keys: providers.Keyring, persona: judging.CallerPersona
) -> providers.Running:
    """The stage that improvises the caller's lines."""
    row = None if configured.caller is None else configured.caller.llm
    declared = tuning.model_named(persona.llm or None, "llm", in_use=configured.default_vendors["llm"]) or (
        None if row is None else Model(provider=row.vendor, model=row.model or "")
    )
    return providers.stage_on_its_key("llm", declared, configured, keys)


# `tts` names a vendor, never a model: the persona's, else the one in use.
def voice_vendor(configured: providers.Catalog, persona: judging.CallerPersona | None) -> tuple[str, str | None]:
    """The vendor and the model the caller's voice is of."""
    in_use = configured.default_vendors["tts"]
    chosen = None if persona is None else tuning.model_named(persona.tts or None, "tts", in_use=in_use)
    return (in_use, None) if chosen is None else (chosen.provider, chosen.model or None)


# Read in a transaction of its own: the model is held for a whole call, and no connection is.
@asynccontextmanager
async def caller_model(
    serving: calls.Serving, scope: Scope, persona: judging.CallerPersona
) -> AsyncGenerator[CallerModel]:
    """The model that improvises the caller's lines: the persona's, else the box's caller's."""
    async with serving.handles.sessions.begin() as session_:
        configured = await providers.get_catalog(session_)
        keys = await providers.keys_of(session_, serving.handles.vault, scope)
    stage = caller_stage(configured, keys, persona)
    model = providers.llm_of(stage)
    try:
        yield CallerModel(model, named(stage))
    finally:
        await model.aclose()


# The caller speaks in the agent's language and never in the agent's own voice.
async def caller_voice(
    session_: AsyncSession, serving: calls.Serving, scope: Scope, agent: str, persona: judging.CallerPersona | None
) -> providers.Running:
    """The caller's voice: the persona's, else one of the vendor's that is not the agent's."""
    configured = await providers.get_catalog(session_)
    holding = serving.registry.serving(scope, agent, None)
    config = AgentConfig(slug=agent)
    if holding is not None and holding.scope.org == scope.org:
        config, _ = await settings.tuned_for_call(session_, holding.config, holding.scope, configured)
    vendor, model = voice_vendor(configured, persona)
    keys = await providers.keys_of(session_, serving.handles.vault, scope)
    agents = _voice_the_agent_speaks(config, configured, keys, vendor)
    chosen = spoken.pick_caller_voice(
        configured.voices, vendor, agents, config.language, None if persona is None else persona.voice
    )
    unnamed = providers.stage_on_its_key("tts", Voice(provider=vendor, model=model), configured, keys)
    if chosen is None:
        chosen = await _another_listed(configured, unnamed, agents, config.language)
    stage = providers.stage_on_its_key("tts", Voice(provider=vendor, model=model, voice_id=chosen), configured, keys)
    return dataclasses.replace(stage, voice=chosen, language=config.language)


# The voice the agent speaks with on the caller's vendor: the one it declared, else the operator's
# for its language, else its plugin's own default, which is what its pipeline gives it; on another
# vendor no voice of the caller's can be the agent's.
def _voice_the_agent_speaks(
    config: AgentConfig, configured: providers.Catalog, keys: providers.Keyring, vendor: str
) -> str | None:
    declared = config.voice or Voice(provider=configured.default_vendors["tts"])
    if declared.provider != vendor:
        return None
    row = configured.voices.get(f"{vendor}/{providers.primary_language(config.language)}")
    if declared.voice_id or row:
        return declared.voice_id or row
    return providers.default_voice(providers.stage_on_its_key("tts", declared, configured, keys))


# The operator gave no voice the agent is not speaking in: the vendor's own, the row's listing
# first, in the agent's language before any other. A vendor that lists none leaves the plugin's.
async def _another_listed(
    configured: providers.Catalog, unnamed: providers.Running, agents: str | None, language: str | None
) -> str | None:
    spoken_in = providers.primary_language(language)
    try:
        listed = providers.listed_in_catalog(configured, unnamed.vendor, spoken_in) or await providers.listed_by_vendor(
            dataclasses.replace(unnamed, language=spoken_in)
        )
    except PinecallError:
        logger.warning(NONE_LISTED, unnamed.vendor, exc_info=True)
        return None
    others = [voice for voice in listed if voice.id != agents]
    same_language = [voice for voice in others if _speaks(voice, spoken_in)]
    found = (same_language or others)[:1]
    return found[0].id if found else None


def _speaks(voice: providers.ListedVoice, language: str | None) -> bool:
    its_own = str(voice.detail.get("language") or "")
    return language is None or its_own == "" or its_own.startswith(language)
