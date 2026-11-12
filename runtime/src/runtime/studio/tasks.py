"""Studio's loops: the word that an org's agents changed followed, and a look at every one of them each minute."""

from runtime.enums import Env
from runtime.hosting import service as hosting
from runtime.kit.loops import loop, survive
from runtime.signal import Signal
from runtime.studio.service.holder import Holder

# How soon a gateway listens again once the signal was lost and is back.
LISTEN_AGAIN_S = 1.0
# How often every Studio agent of the box is looked at, whatever was said.
LOOKED_EVERY_S = 60.0


# One pass is one listening, from the signal coming up to the signal being lost. It begins with a look
# at every agent: at the gateway's start that is what holds them, off the lifespan, so the gateway
# answers before it has registered a box's worth of agents; after the signal was lost it is what
# mends every word that was not heard. Until 2026-11 a lost word was a definition never held.
@loop("studio-changes", every_s=LISTEN_AGAIN_S)
async def follow_changes(holder: Holder, signal: Signal) -> None:
    """Hold again the Studio agents of each org another gateway, or this one, says changed."""
    await signal.wait_until_up()
    listener = await signal.subscribe(hosting.APPS_CHANGED)
    try:
        await holder.reconcile()
        async for data in listener:
            named = data.decode(errors="replace")
            with survive("holding again the Studio agents that changed", named):
                org, _, env = named.partition("|")
                await holder.refresh(org, Env(env))
    finally:
        listener.close()


# The word is a hint and this is the guarantee: an agent a socket refused, or a save whose word was
# lost while the listener still stood, is held within the minute.
@loop("studio-look", every_s=LOOKED_EVERY_S)
async def look_at_agents(holder: Holder) -> None:
    """Hold every Studio agent of the box as its newest release says."""
    await holder.reconcile()
