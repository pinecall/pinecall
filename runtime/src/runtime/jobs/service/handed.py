"""What a developer hears while their ring crosses to the sandbox: one sentence, said by production's worker."""

import asyncio

from livekit.agents import JobContext
from livekit.agents.voice import Agent, AgentSession

from runtime.actor import Scope
from runtime.jobs.service.client import GatewayClient
from runtime.kit.loops import survive
from runtime.providers import service as providers

# The leg to the sandbox takes two or three seconds to answer, and livekit-sip answers the caller as
# that leg starts to dial: until 0.11.39 a developer heard those seconds as silence, and took the
# line for dead. Production's worker is in the room until the leg answers, so it says where the
# ring is going, in the agent's own voice.
HANDED_SAYS = "Redirecting you to your sandbox."
# Past this the sentence is given up: the ring is handed over whether it was said or not.
SAID_WITHIN_S = 8.0


async def tell_it_is_handed(ctx: JobContext, gateway: GatewayClient, agent: str, scope: Scope) -> None:
    """Say the sentence to the caller in the room; a voice that cannot be had says nothing, and the ring goes on."""
    with survive("telling a developer their ring is handed to the sandbox", ctx.room.name):
        async with asyncio.timeout(SAID_WITHIN_S):
            stages = await gateway.get_stages(agent, scope)
            speaking: AgentSession[None] = AgentSession(tts=providers.tts_of(stages.pipeline.tts))
            await speaking.start(Agent(instructions=HANDED_SAYS), room=ctx.room, record=False, session_host=False)  # pyright: ignore[reportUnknownMemberType]
            try:
                await speaking.say(HANDED_SAYS, allow_interruptions=False)
            finally:
                await speaking.aclose()
