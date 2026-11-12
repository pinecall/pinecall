"""A call's lookup of what its org knows: recall or search for one turn, written on its log."""

import time
from dataclasses import dataclass

from runtime.kit.text import JsonObject
from runtime.knowledge import service as knowledge
from runtime.live.parts import LiveParts
from runtime.live.served import Served
from runtime.wire.parts import PlatformTool


@dataclass(frozen=True, slots=True)
class Found:
    """What a lookup found, as the model reads it, and how long finding it took."""

    output: JsonObject
    took_ms: float


# The quotas and the embedder are read per lookup, so a plan changed mid-call applies from the next
# turn; no connection is held while the embedder answers (`knowledge.look_up`).
async def look_up(
    live: LiveParts, served: Served, tool: PlatformTool, arguments: JsonObject, speech: str | None
) -> Found:
    """Recall or search for a call served here, written on its log, answered as the model reads."""
    started = time.perf_counter()
    call = knowledge.LookupCall(
        scope=served.scope,
        call=served.call,
        channel=served.context.channel,
        contact=served.context.remembered_as,
        declaration=served.declaration,
        log=served.log,
        now=live.now,
    )
    asked = knowledge.LookupRequest(tool=tool, input=arguments, speech_id=speech)
    answer = await knowledge.look_up(live.sessions, live.vault, live.http, call, asked)
    return Found(answer.dump(), (time.perf_counter() - started) * 1000)
