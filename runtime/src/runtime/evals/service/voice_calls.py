"""A spoken call placed and held to its end: the room the client named, the persona played on it, what it cost."""

from dataclasses import dataclass, field

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.billing import service as billing
from runtime.evals.parts import Harness
from runtime.evals.service.leg import describe
from runtime.evals.service.simulated_calls import Simulation, play_spoken
from runtime.evals.service.simulations import (
    act_as_asked,
    admit_simulation,
    claim_new_call,
    find_persona,
    get_number_to_ring,
    refuse_an_opened_call,
)
from runtime.judging import service as judging
from runtime.kit.link import LinkShape
from runtime.kit.text import Json, JsonObject
from runtime.providers import service as providers


@dataclass(frozen=True, slots=True)
class VoiceCall:
    """A spoken call the CLI places and waits for: the room it minted, the agent, the caller, the line."""

    call: str
    agent: str
    persona: judging.Persona
    turns: int = 6
    interferer_db: float | None = None
    packet_loss: float = 0.0
    ambience: str | None = None
    pause_s: float | None = None
    # The caller rings the agent by phone, and the network its packets cross: as a simulation's.
    by_phone: bool = False
    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    rate_kbps: float | None = None
    # The state the agent opens the call in: the persona's, as `pinecall simulate` reads it.
    state: JsonObject = field(default_factory=dict[str, Json])


@dataclass(frozen=True, slots=True)
class VoicePlayed:
    """A spoken call played to its end: how many lines the caller said, on what line, what it cost."""

    call: str
    turns: int
    line: str
    caller_cost_usd: float
    # The caller hung up because its call had spent the providers row's `caller.ceiling_usd`.
    stopped_at_ceiling: bool


# The same simulation as `place_simulation` places, on a room the client named, and answered when the
# caller has hung up. A persona is the agent's own or Pinecall's library's: a name that is neither is
# refused; one sent without a name is played as sent. The id is refused before it is given a place:
# until 2026-11 it was admitted first, and an id sent twice took the place of the call playing under it.
async def place_voice_call(parts: Harness, actor: Actor, asked: VoiceCall) -> VoicePlayed:
    """Dispatch the agent into a room, play the persona as a spoken caller, and hang up."""
    accounts.check_agent(actor, asked.agent)
    scope, persona = actor.scope, asked.persona
    async with parts.sessions.begin() as session_:
        if persona.name:
            await find_persona(session_, scope, asked.agent, persona.name)
        judging.check_persona_models(await providers.get_catalog(session_), persona.llm, persona.tts, persona.voice)
        quotas = await billing.get_quotas(session_, scope.org, scope.env)
        await refuse_an_opened_call(session_, asked.call)
    # A ring with nobody to answer it would wait forty seconds for an agent that never joins.
    parts.apps.get(scope, asked.agent)
    acts = act_as_asked(persona.behavior, asked.interferer_db, asked.packet_loss, asked.ambience, asked.pause_s)
    network = LinkShape(acts.packet_loss, asked.delay_ms, asked.jitter_ms, asked.rate_kbps)
    async with parts.simulations.hold_place(asked.call, scope, quotas.simulating_at_most):
        async with parts.sessions.begin() as session_:
            await admit_simulation(session_, parts, scope, asked.agent, persona, spoken=True)
            rings = await get_number_to_ring(session_, parts, scope, asked.agent) if asked.by_phone else None
            await claim_new_call(session_, asked.call, asked.agent, scope)
        simulation = Simulation(
            call=asked.call,
            agent=asked.agent,
            scope=scope,
            persona=persona,
            turns=asked.turns,
            spoken=True,
            acts=acts,
            state=dict(asked.state),
            network=network,
            rings=rings,
        )
        played = await play_spoken(parts, simulation)
    line = describe(acts, network, by_phone=asked.by_phone)
    return VoicePlayed(asked.call, played.turns, line, played.spending.usd, played.spending.is_over)
