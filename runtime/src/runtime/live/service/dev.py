"""The console's asks relayed to a running app: chat, knowledge, memory, the view, evals."""

import asyncio
from dataclasses import dataclass
from typing import get_args
from uuid import uuid4

from runtime.actor import Scope
from runtime.exceptions import NotFound, PinecallError
from runtime.kit.text import JsonObject
from runtime.live.holders import Holders, NoApp, NobodyTakes, NoDevAnswerer, NotThatApp, Registration
from runtime.live.sockets import SocketId, Sockets
from runtime.wire.base import Entry
from runtime.wire.events import DevRequest
from runtime.wire.parts import DevVerb

# Longer than any verb takes: a suite waits 20 s on the app's side.
ANSWERED_WITHIN_S = 120.0
ASK_PREFIX = "dev_"
# The family whose verb the class serving the call draws; every other is answered by the CLI beside it.
THE_VIEW = "view"

NAMED_FAMILIES: dict[str, frozenset[str]] = {
    "chat": frozenset({"chat.roster", "chat.start", "chat.say", "chat.end"}),
    "knowledge": frozenset({"knowledge.roster", "knowledge.push", "knowledge.eval"}),
    "memory": frozenset({"memory.roster", "memory.eval", "memory.extraction"}),
    THE_VIEW: frozenset({"view.render"}),
}
EVERY_VERB: frozenset[str] = frozenset(get_args(DevVerb.__value__))
# Every verb no other family names is an eval's.
FAMILIES: dict[str, frozenset[str]] = {
    **NAMED_FAMILIES,
    "evals": EVERY_VERB - frozenset().union(*NAMED_FAMILIES.values()),
}


class AppRefused(PinecallError):
    """The app answered the ask with a refusal of its own, or did not answer: its status stands."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status


@dataclass(frozen=True, slots=True)
class Relay:
    """Which family's verb, of which agent, and the app named to answer it when one is."""

    family: str
    slug: str
    verb: str
    app: SocketId | None = None


# dev.request goes down the socket unstored; the app's refusal comes back as its own status. The ask is
# forgotten whole however it ends: cancelled here, it is dropped by the sockets that kept it.
async def relay(sockets: Sockets, holders: Holders, scope: Scope, asked: Relay, said: JsonObject) -> JsonObject:
    """Ask the process answering the console for the agent, and hand its answer back."""
    if asked.verb not in FAMILIES[asked.family]:
        raise NotFound(f"no dev verb {asked.verb} in {asked.family}: the verbs are {sorted(FAMILIES[asked.family])}")
    registration = _find_answering(holders, scope, asked)
    ask_id = f"{ASK_PREFIX}{uuid4().hex[:12]}"
    request = DevRequest.parse({"id": ask_id, "verb": asked.verb, "data": said}, "dev.request")
    waiting = await sockets.ask(ask_id)
    if not await sockets.tell(registration.owner, Entry.make_unstored(asked.slug, "dev.request", request.dump())):
        waiting.cancel()
        raise AppRefused(502, f"the app holding agent {asked.slug} disconnected before it answered {asked.verb}")
    try:
        answer = await asyncio.wait_for(waiting, ANSWERED_WITHIN_S)
    except TimeoutError:
        waiting.cancel()
        raise AppRefused(
            504, f"the app holding agent {asked.slug} did not answer {asked.verb} within {ANSWERED_WITHIN_S:.0f}s"
        ) from None
    if answer.refused is not None:
        raise AppRefused(answer.refused.status, answer.refused.detail)
    return answer.result or {}


# The panel is drawn by the class serving the call; every other verb by the CLI beside it.
def _find_answering(holders: Holders, scope: Scope, asked: Relay) -> Registration:
    if asked.app is not None:
        named = holders.find_serving(scope, asked.slug, asked.app)
        if named is None:
            raise NotThatApp(asked.app, asked.slug)
        return named
    draws = asked.family == THE_VIEW
    found = holders.find_serving(scope, asked.slug) if draws else holders.find_dev_answerer(scope, asked.slug)
    if found is not None:
        return found
    if holders.find_holder(scope, asked.slug) is None:
        raise NoApp(asked.slug)
    raise NobodyTakes(asked.slug) if draws else NoDevAnswerer(asked.slug)
