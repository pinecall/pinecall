"""The flows' loop: the clock that ends a run's sleep or its wait, and the look at the calls its runs placed."""

import asyncio

from pinecall_runtime.flows import service
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.kit.loops import survived

# A run wakes within this of its hour, and hears of its call's end within it.
WOKEN_EVERY_S = 2.0


# Each look is a transaction of its own: what one wakes, an app's process may take at once.
async def wake_forever(handles: Handles) -> None:
    """A pass now, and one every two seconds."""
    while True:
        with survived("the waking of the runs whose sleep or wait is over"):
            async with handles.sessions() as session, session.begin():
                await service.wake_due(session)
        with survived("the waking of the runs whose call ended"):
            async with handles.sessions() as session, session.begin():
                await service.wake_called(session)
        await asyncio.sleep(WOKEN_EVERY_S)
