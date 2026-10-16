"""The console's asks relayed to a running app: chat, knowledge, memory, the view, evals."""

import asyncio
from dataclasses import dataclass
from typing import get_args
from uuid import uuid4

from pinecall_runtime.agents.service import registry as agents_registry
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.exceptions import NotFound, PinecallError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import DevRequest
from pinecall_runtime.wire.parts import DevVerb

NO_SUCH_VERB = "no dev verb {verb} in {family}: the verbs are {verbs}"
NO_ANSWER = "the app holding agent {slug} did not answer {verb} within {seconds:.0f}s"
APP_LEFT = "the app holding agent {slug} disconnected before it answered {verb}"
# Longer than any verb takes: a suite waits 20 s on the app's side.
ANSWERED_WITHIN_S = 120.0
ASK_PREFIX = "dev_"

NAMED_FAMILIES: dict[str, frozenset[str]] = {
    "chat": frozenset({"chat.roster", "chat.start", "chat.say", "chat.end"}),
    "knowledge": frozenset({"knowledge.roster", "knowledge.push", "knowledge.eval"}),
    "memory": frozenset({"memory.roster", "memory.eval", "memory.extraction"}),
    "view": frozenset({"view.render"}),
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
    """Which family's verb, of which agent."""

    family: str
    slug: str
    verb: str


# dev.request goes down the socket unstored; the app's refusal comes back as its own status.
async def relay(
    serving: Serving, scope: Scope, asked: Relay, said: JsonObject, app: agents_registry.SocketId | None
) -> JsonObject:
    """Ask the process answering the console for the agent, and hand its answer back."""
    if asked.verb not in FAMILIES[asked.family]:
        raise NotFound(NO_SUCH_VERB.format(verb=asked.verb, family=asked.family, verbs=sorted(FAMILIES[asked.family])))
    registration = _answering(serving.registry, scope, asked, app)
    ask_id = f"{ASK_PREFIX}{uuid4().hex[:12]}"
    request = DevRequest.model_validate({"id": ask_id, "verb": asked.verb, "data": said})
    live = serving.live
    waiting = await live.ask(ask_id)
    if not await live.tell(registration.owner, Entry.unstored(asked.slug, "dev.request", request.dump())):
        live.pending_answers.pop(ask_id, None)
        waiting.cancel()
        raise AppRefused(502, APP_LEFT.format(slug=asked.slug, verb=asked.verb))
    try:
        answer = await asyncio.wait_for(waiting, ANSWERED_WITHIN_S)
    except TimeoutError:
        live.pending_answers.pop(ask_id, None)
        waiting.cancel()
        raise AppRefused(504, NO_ANSWER.format(slug=asked.slug, verb=asked.verb, seconds=ANSWERED_WITHIN_S)) from None
    if answer.refused is not None:
        raise AppRefused(answer.refused.status, answer.refused.detail)
    return answer.result or {}


# The panel is drawn by the class serving the call; every other verb by the CLI beside it.
def _answering(
    registry: agents_registry.AgentRegistry, scope: Scope, asked: Relay, app: agents_registry.SocketId | None
) -> agents_registry.Registration:
    if app is not None:
        named = registry.serving(scope, asked.slug, app)
        if named is None:
            raise agents_registry.NotThatApp(app, asked.slug)
        return named
    found = (
        registry.serving(scope, asked.slug, None)
        if asked.family == "view"
        else registry.answering_dev(scope, asked.slug)
    )
    if found is not None:
        return found
    if registry.holder_of(scope, asked.slug) is None:
        raise agents_registry.NoApp(asked.slug)
    raise (
        agents_registry.NobodyTakes(asked.slug) if asked.family == "view" else agents_registry.NoDevAnswerer(asked.slug)
    )
