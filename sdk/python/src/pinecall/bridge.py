"""`mount`: a class on a client, one instance per call, sending only what changed."""

import asyncio
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pinecall import (
    _accepts,
    _asking,
    _author,
    _config,
    _harness,
    _melody,
    _running,
    _searching,
    _state,
    _tools,
)
from pinecall._agent_socket import AgentSocket, Tool
from pinecall._calls import Call
from pinecall._cause import cause_of
from pinecall._config import slug_of
from pinecall._failures import hooked
from pinecall._handoff import ROUTED, Answering, Team, answered_by, team_tools
from pinecall._live import Live
from pinecall._passing import become, passed, runner
from pinecall._screened import scene_tools, screen_declared, screens, turned, unscreened
from pinecall._sending import line_of, recalled, searching, state_of, synced
from pinecall.agent import Agent, EventMeta, LastCall
from pinecall.blocks import LAYOUT
from pinecall.call import CallWorld
from pinecall.client import Client
from pinecall.screen import TASK_GIVE
from pinecall.tasks import Task
from pinecall.wire._names import JsonObject
from pinecall.wire.config import AgentConfig
from pinecall.wire.events_call import CallAttached, CallStarted
from pinecall.wire.events_turn import EventReceived, MemoryOps
from pinecall.wire.frames import WireModel
from pinecall.wire.parts import ToolSpec

logger = logging.getLogger("pinecall")


@dataclass(frozen=True)
class Mounted:
    """A class mounted on a client: its socket's agent, and the instances serving live calls."""

    slug: str
    agent: AgentSocket
    live: dict[str, Live]

    def instance_of(self, call: str) -> Agent | None:
        """The instance serving `call`, while it lasts."""
        held = self.live.get(call)
        return None if held is None else held.agent


def mount(  # noqa: PLR0913 - one keyword for each thing a voice app adds to its agent
    cls: type[Agent],
    client: Client,
    *,
    slug: str | None = None,
    takes_unclaimed: bool = True,
    last: LastCall | None = None,
    declares: Mapping[str, object] | None = None,
    team: Team | None = None,
    rules: Sequence[str] = (),
    answers: Answering | None = None,
) -> Mounted:
    """Hold a class on a client, an instance of its own per call; nothing leaves before `connect`.

    Args:
        cls: the agent's class.
        client: the socket it is held on.
        slug: the name it registers as; left out, the class's own.
        takes_unclaimed: a console's process says no: it serves only the calls it opened.
        last: where `last(contact)` reads a contact's previous call from.
        declares: what its voice app adds to its declaration: its line's greeting, a silence.
        team: the agents a call of this one may pass between, itself among them, with slugs.
        rules: the rules its voice app gives every agent of it, read into its prompt.
        answers: its line's function that picks who of the team serves each call.
    """
    live: dict[str, Live] = {}
    loop = asyncio.get_running_loop()
    declared = Declaration.of(cls, team, declares or {})
    tools = [Tool(spec, runner(live, spec.name)) for spec in declared.tools]
    tasks, draws = declared.tasks, declared.draws
    held = client.agent(
        slug or slug_of(cls),
        declared.config,
        tools,
        takes_unclaimed=takes_unclaimed,
        says_done=True,
    )

    def serve(call: Call) -> Live:
        world = CallWorld(
            line_of(call), lambda type_, data: held.command(type_, call.id, data),
            searching(client, call), loop,
        )  # fmt: skip
        asking = _asking.Asking(tasks)
        agent = cls().seal()
        served = Live(agent, cls, world, call, asking, team, rules, last, draws)
        become(served, cls, agent)
        world.asked_by(asking.ask, lambda: asking.asked)
        world.shown_by(lambda: shown(live, served))
        if team is not None:
            world.passed_by(lambda to, data: passed(served, to, data, follow))
        live[call.id] = served
        asyncio.ensure_future(work(served))  # noqa: RUF006 - it ends with the call, which ends it
        return served

    def started(event: WireModel, call: Call | None) -> None:
        if isinstance(event, CallStarted) and call is not None:
            served = serve(call)
            served.jobs.put_nowait(lambda: opening(served, event.state, answers))

    def attached(event: WireModel, call: Call | None) -> None:
        if not isinstance(event, CallAttached) or call is None:
            return
        served = live.get(call.id)
        if served is not None:
            # Served here already (the gateway restarted): the whole prompt again; it may be lost.
            served.jobs.put_nowait(lambda: resent(served))
            return
        served = serve(call)
        served.jobs.put_nowait(lambda: adopted(served, dict(event.state)))

    def ended(_: WireModel, call: Call | None) -> None:
        served = None if call is None else live.pop(call.id, None)
        if served is not None:
            served.asking.abandon()
            served.jobs.put_nowait(lambda: finished(served))
            served.jobs.put_nowait(None)

    held.on("call.started", started)
    held.on("call.attached", attached)
    held.on("call.ended", ended)
    return Mounted(held.slug, held, live)


@dataclass(frozen=True)
class Declaration:
    """What a mounted class tells the gateway: its declaration, its tools, its tasks and screen."""

    config: AgentConfig
    tools: list[ToolSpec]
    tasks: list[Task[object]]
    draws: bool

    @staticmethod
    def of(agent: type[Agent], team: Team | None, declares: Mapping[str, object]) -> "Declaration":
        """The class's, with what its team shares and what its voice app adds."""
        cls = agent
        classes: list[type] = list(team) if team else [cls]
        registry: dict[str, _tools.Declared] = getattr(cls, "_pinecall_tools")  # noqa: B009
        own = team_tools(team) if team else [one.spec for one in registry.values()]
        taken = [spec.name for spec in own]
        tasks = _asking.tasks_on(cls, classes if team else ())
        tools = [*own, *_asking.giving_tools(tasks, taken), *scene_tools(classes, taken)]
        draws = screens(classes, Agent)
        declared = config_of(cls).model_dump(by_alias=True, exclude_unset=True)
        if draws:
            declared = screen_declared(declared, tasks=bool(tasks))
        return Declaration(
            AgentConfig.model_validate({**declared, **declares}), tools, tasks, draws
        )


def shown(live: Mapping[str, Live], served: Live) -> None:
    """Something was put on the page: drawn again, while this instance still serves its call."""
    if live.get(served.call.id) is served:
        synced(served)


def config_of(cls: type[Agent]) -> AgentConfig:
    """What the class declares: its layout, what it searches, shows and accepts, what it runs on."""
    declared: dict[str, object] = {
        **_config.environment_of(cls),
        **_harness.harness_of(cls),
        # The melody the class ships, named by its hash.
        **_melody.hold_config_of(cls),
        "prompt": [spec.written() for spec in LAYOUT],
    }
    if _searching.searches(cls):
        declared["uses_knowledge"] = True
    fields = _state.visibilities_of(getattr(cls, _state.FIELDS))
    if fields:
        declared["state_fields"] = [one.written() for one in fields]
    events = _accepts.specs_of(getattr(cls, "_pinecall_events"))  # noqa: B009 - the class's own
    if events:
        declared["events"] = [one.written() for one in events]
    panel = getattr(cls, "_pinecall_panel")  # noqa: B009 - the class's own
    if panel is not None:
        # Only the name: the panel is drawn when a console asks (`view.render`).
        declared["view"] = {"name": panel.name}
    return AgentConfig.model_validate(declared)


async def work(served: Live) -> None:
    """Run the call's jobs one at a time, in the order they came, until the call ends."""
    while (job := await served.jobs.get()) is not None:
        served.busy = True
        try:
            await job()
        except Exception:
            logger.exception("pinecall: %s", served.call.id)
        finally:
            served.busy = False


# The line chooses while the caller hears its greeting. The state the opener asked for is applied
# after on_call, which would overwrite it, and before the first render; one prompt, not one a field.
async def opening(served: Live, state: JsonObject | None, answers: Answering | None) -> None:
    """Choose who serves, run `on_call`, open in the state asked for, send it all, then follow."""
    if answers is not None and served.team is not None:
        first = await answered_by(answers, line_of(served.call), served.cls, served.team)
        if first.agent is not served.cls or first.why is not None:
            said: JsonObject = {"to": served.team.get(first.agent, "")}
            served.call.log(ROUTED, said if first.why is None else {**said, "why": first.why})
        if first.agent is not served.cls:
            served.stops.pop("log", lambda: None)()
            become(served, first.agent)
    author = _author.hook("on_call")
    await hooked(served.call, "on_call", _running.run(author, served.agent.on_call, served.world))
    wrote = any(change.author == author for change in served.agent.changes())
    if state:
        served.agent.start_in(state)
    # The prompt before the state: the caller's first turn needs the prompt, only the log reads
    # the state, and a state with a pii field is sealed before the gateway reads the next command.
    synced(served)
    cause = cause_of(author, served.world) if wrote else None
    served.call.set_state(state_of(served), cause=cause)
    follow(served)


async def adopted(served: Live, state: JsonObject) -> None:
    """A call handed over mid-call: the state the gateway kept, no `on_call`, all of it sent."""
    served.resumed = True
    served.agent.restore(unscreened(state))
    synced(served)
    follow(served)


async def resent(served: Live) -> None:
    """Forget what was sent, and send the whole prompt again."""
    with served.lock:
        served.sent.clear()
        served.tools_shown = None
    synced(served)


async def finished(served: Live) -> None:
    """Stop rendering; `on_end` runs with the log still open, so a farewell line lands."""
    for kind in ("state", "entries"):
        served.stops.pop(kind, lambda: None)()
    ending = _running.run(_author.hook("on_end"), served.agent.on_end, served.world)
    await hooked(served.call, "on_end", ending)
    served.stops.pop("log", lambda: None)()
    served.agent.serving(None)
    # After every line the hook logged, whether it ran or raised: the gateway seals the call on this
    # word, and a line sent after the seal is refused.
    served.call.done()


def follow(served: Live) -> None:
    """From now on: every write is sent with its cause, every entry folded in."""
    agent, world, call = served.agent, served.world, served.call

    def changed(change: _state.Change) -> None:
        call.set_state(state_of(served), [change.field], cause_of(change.author, world))
        synced(served)

    def heard(type_: str, event: WireModel, _: Call) -> None:
        world.take(event, time.time())
        if isinstance(event, EventReceived):
            received(served, event)
        elif isinstance(event, MemoryOps):
            # Now, not queued: the runtime holds the model's turn while the recall runs, and the
            # view must say what the answer changes before that turn is taken.
            served.remembered = recalled(event)
            synced(served)
            served.jobs.put_nowait(lambda: remembered(served, event))
        # The view answers the turn being taken; a claim lets the caller see the page.
        if turned(type_, world, served.screened) or type_ in ("turn.user", "call.claimed"):
            synced(served)

    served.stops |= {"state": agent.on_change(changed), "entries": call.on_any(heard)}


async def remembered(served: Live, ops: MemoryOps) -> None:
    """Hand what memory read or wrote to `on_memory`, after the view already says it."""
    running = _running.run(
        _author.hook("on_memory"), served.agent.on_memory, list(ops.ops), served.world
    )
    await hooked(served.call, "on_memory", running)


def received(served: Live, fact: EventReceived) -> None:
    """An outside event reaches `on_event` only from a sender the class accepts; one at a time."""
    if fact.name == TASK_GIVE and fact.source == "participant":
        served.jobs.put_nowait(lambda: given_by_page(served, dict(fact.data)))
        return
    events = getattr(served.cls, "_pinecall_events")  # noqa: B009 - the class's own
    if not _accepts.takes(events, fact.name, fact.source):
        if fact.name not in served.warned:
            served.warned.add(fact.name)
            logger.warning(
                "pinecall: %s from %s is not one this agent accepts; dropped",
                fact.name,
                fact.source,
            )
        return
    meta = EventMeta(fact.source, served.call.seq, fact.identity)

    async def run() -> None:
        served.world.cause = (fact.name, meta.seq)
        try:
            running = _running.run(
                _author.event(fact.name), served.agent.on_event, fact.name, dict(fact.data), meta
            )
            await hooked(served.call, "on_event", running, event=fact.name)
        finally:
            served.world.cause = None

    served.jobs.put_nowait(run)


async def given_by_page(served: Live, data: JsonObject) -> None:
    """The page answered a task: the waiting tool goes on, the model is told, the form redrawn."""
    told = await served.asking.given_by_page(data.get("task"), data.get("given"))
    if told is not None:
        served.world.reply(told)
    synced(served)
