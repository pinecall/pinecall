"""Telephony's loop: the SFU brought level with the tables when a gateway starts."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.kit.crypto import Vault
from runtime.kit.loops import loop
from runtime.livekit import Servers
from runtime.telephony.service import rebuild
from runtime.telephony.service.carrier import SipNames

# A LiveKit still starting beside the gateway answers in seconds; one that is down, in minutes: a
# pass that leaves an org owed raises, and the process's `Loops` waits twice as long before the
# next, a minute at most.
REBUILT_EVERY_S = 2.0


# Until 2026-11 this was a task of its own, started outside the process's loops: a rebuild that died
# showed nowhere but the log. Once nothing is owed a pass does nothing, and the loop's heartbeat goes on.
@loop("sip", every_s=REBUILT_EVERY_S)
async def rebuild_sip(
    owed: rebuild.Owed,
    sessions: async_sessionmaker[AsyncSession],
    vault: Vault,
    servers: Servers,
    names: SipNames,
) -> None:
    """Admit on the SFU every routed number it still owes the tables."""
    if owed.nothing:
        return
    async with sessions() as session:
        rebuilt = await rebuild.rebuild(session, vault, servers, names, owed)
        await session.commit()
    owed.settle(rebuilt)
