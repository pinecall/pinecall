"""The loop accounts owns: this gateway hearing the keys the others revoked."""

from runtime.accounts.service.key_cache import FORGET_CHANNEL, KeyCache
from runtime.kit.loops import loop, survive
from runtime.signal import Signal

# How soon a gateway listens again once the signal was lost and is back.
LISTEN_AGAIN_S = 1.0


# One pass is one listening, from the signal coming up to the signal being lost; the next pass waits
# for it to be back. A pass that raised is said and counted by the process's loops, where the old
# listener was a bare task: once it died, nothing said so, and every key another gateway revoked
# stayed trusted here for as long as the cache kept it.
@loop("revocations", every_s=LISTEN_AGAIN_S)
async def hear_revocations(cache: KeyCache, signal: Signal) -> None:
    """Forget here every key another gateway says it revoked, until the signal is lost."""
    await signal.wait_until_up()
    listener = await signal.subscribe(FORGET_CHANNEL)
    # What was revoked while the signal was away is unknown: nothing from before is trusted.
    cache.clear()
    try:
        async for data in listener:
            # A revocation that cannot be read is said and the next is heard: the listener that died
            # with it would leave every revoked key trusted for as long as it is kept.
            with survive("reading a revocation of another gateway"):
                cache.hear(data)
    finally:
        listener.close()
