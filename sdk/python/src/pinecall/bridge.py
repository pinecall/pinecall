"""`mount`: a class on a client, one instance per call, sending only what changed."""

import asyncio
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import TypeAdapter

from pinecall import _accepts, _config, _running, _searching, _state, _tools
from pinecall._agent_socket import AgentSocket, Tool
from pinecall._calls import Call
from pinecall._config import slug_of
from pinecall.agent import Agent, EventMeta, LastCall, Logged
from pinecall.blocks import LAYOUT, render
from pinecall.call import CallLine, CallWorld
from pinecall.client import Client, Found
from pinecall.errors import ToolFailed
from pinecall.wire._names import JsonObject
from pinecall.wire.events_call import CallAttached, CallStarted
from pinecall.wire.events_turn import EventReceived, MemoryOps
from pinecall.wire.frames import WireModel
from pinecall.wire.parts import AgentConfig, ToolSpec

logger = logging.getLogger("pinecall")

# Whatever a tool returns or a field holds, made JSON: dataclasses, models, dates, tuples.
ANYTHING: TypeAdapter[object] = TypeAdapter(object)

Job = Callable[[], Awaitable[None]]


@dataclass
class Live:
    """One served call: its instance, what was last sent for it, and its jobs, run in order."""

    agent: Agent
    world: CallWorld
    call: Call
    sent: dict[str, str] = field(default_factory=dict[str, str])
    tools_shown: str | None = None
    remembered: list[str] = field(default_factory=list[str])
    stops: dict[str, Callable[[], None]] = field(default_factory=dict[str, Callable[[], None]])
    warned: set[str] = field(default_factory=set[str])
    # A tool's thread and the loop may both sync: what was sent is read and written under it.
    lock: threading.Lock = field(default_factory=threading.Lock)
    jobs: asyncio.Queue[Job | None] = field(default_factory=asyncio.Queue[Job | None])
    busy: bool = False
    """Whether one of its jobs is running now."""


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


def mount(
    cls: type[Agent],
    client: Client,
    *,
    slug: str | None = None,
    takes_unclaimed: bool = True,
    last: LastCall | None = None,
) -> Mounted:
    """Hold a class on a client, an instance of its own per call; nothing leaves before `connect`.

    Args:
        cls: the agent's class.
        client: the socket it is held on.
        slug: the name it registers as; left out, the class's own.
        takes_unclaimed: a console's process says no: it serves only the calls it opened.
        last: where `last(contact)` reads a contact's previous call from.
    """
    live: dict[str, Live] = {}
    loop = asyncio.get_running_loop()
    declared: dict[str, _tools.Declared] = getattr(cls, "_pinecall_tools")  # noqa: B009 - the class's own
    tools = [Tool(one.spec, runner(cls, live, one.spec)) for one in declared.values()]
    held = client.agent(
        slug or slug_of(cls), config_of(cls), tools, takes_unclaimed=takes_unclaimed
    )

    def serve(call: Call) -> Live:
        agent = cls().seal()
        if last is not None:
            agent.reads_last_from(last)
        world = CallWorld(
            line_of(call),
            lambda type_, data: held.command(type_, call.id, data),
            searching(client, call),
            loop,
        )
        served = Live(agent.serving(world), world, call)
        live[call.id] = served
        asyncio.ensure_future(work(served))  # noqa: RUF006 - it ends with the call, which ends it
        return served

    def started(event: WireModel, call: Call | None) -> None:
        if isinstance(event, CallStarted) and call is not None:
            served = serve(call)
            served.jobs.put_nowait(lambda: opening(served, event.state))

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
            served.jobs.put_nowait(lambda: finished(served))
            served.jobs.put_nowait(None)

    held.on("call.started", started)
    held.on("call.attached", attached)
    held.on("call.ended", ended)
    return Mounted(held.slug, held, live)


def config_of(cls: type[Agent]) -> AgentConfig:
    """What the class declares: its layout, what it searches, shows and accepts, what it runs on."""
    declared: dict[str, object] = {
        **_config.environment_of(cls),
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


def runner(
    cls: type[Agent], live: dict[str, Live], spec: ToolSpec
) -> Callable[[JsonObject, Call], Awaitable[object]]:
    """What runs one tool for a call: on the instance serving it, its answer made JSON."""

    async def ran(arguments: JsonObject, call: Call) -> object:
        served = live.get(call.id)
        if served is None:
            raise ToolFailed(f"{spec.name}: this call is no longer being served")
        declared = getattr(cls, "_pinecall_tools")[spec.name]  # noqa: B009 - the class's own
        return ANYTHING.dump_python(
            await _tools.run(served.agent, declared, arguments), mode="json"
        )

    return ran


def searching(client: Client, call: Call) -> Callable[[str, int | None], Awaitable[list[Found]]]:
    """The gateway's search, for this call."""
    return lambda query, k: client.search(call.id, query, k)


def line_of(call: Call) -> CallLine:
    """The call as its first entry said it, for the instance that serves it."""
    contact = call.contact.id if call.contact is not None and call.contact.id else call.from_
    return CallLine(
        id=call.id,
        contact=contact or "",
        from_=call.from_,
        channel=call.channel or "phone",
        medium=call.medium,
        today=call.today,
        claimed=call.claimed,
    )


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


# The state the opener asked for is applied after on_call, which would overwrite it, and before the
# first render, so the model never reads a state the call was not in; one prompt, not one per field.
async def opening(served: Live, state: JsonObject | None) -> None:
    """Run `on_call`, open in the state asked for, send it all, then follow every change."""
    logger.debug("%s: opening", served.call.id)
    await _running.run("hook:on_call", served.agent.on_call, served.world)
    if state:
        served.agent.start_in(state)
    # The prompt before the state: the caller's first turn needs the prompt, only the log reads
    # the state, and a state with a pii field is sealed before the gateway reads the next command.
    synced(served)
    served.call.set_state(jsonable(served.agent.snapshot()))
    logger.debug("%s: opened", served.call.id)
    follow(served)


async def adopted(served: Live, state: JsonObject) -> None:
    """A call handed over mid-call: the state the gateway kept, no `on_call`, all of it sent."""
    served.agent.restore(state)
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
    await _running.run("hook:on_end", served.agent.on_end, served.world)
    served.stops.pop("log", lambda: None)()
    served.agent.serving(None)


def follow(served: Live) -> None:
    """From now on: every write is sent with its cause, every log line, every entry folded in."""
    agent, world, call = served.agent, served.world, served.call

    def logged(line: Logged) -> None:
        call.log(line.name, as_object(line.data))

    def changed(change: _state.Change) -> None:
        call.set_state(jsonable(agent.snapshot()), [change.field])
        # state.set carries no cause: it is logged beside it.
        if world.cause is not None:
            name, seq = world.cause
            call.log(
                "state.cause", {"field": change.field, "kind": "event", "name": name, "seq": seq}
            )
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
        if type_ in ("turn.user", "call.claimed"):
            synced(served)

    served.stops |= {
        "log": agent.on_log(logged),
        "state": agent.on_change(changed),
        "entries": call.on_any(heard),
    }


async def remembered(served: Live, ops: MemoryOps) -> None:
    """Hand what memory read or wrote to `on_memory`, after the view already says it."""
    await _running.run("hook:on_memory", served.agent.on_memory, list(ops.ops), served.world)


def received(served: Live, fact: EventReceived) -> None:
    """An outside event reaches `on_event` only from a sender the class accepts; one at a time."""
    events = getattr(type(served.agent), "_pinecall_events")  # noqa: B009 - the class's own
    if not _accepts.takes(events, fact.name, fact.source):
        if fact.name not in served.warned:
            served.warned.add(fact.name)
            logger.warning(
                "pinecall: %s from %s is not one this agent accepts; dropped",
                fact.name,
                fact.source,
            )
        return
    meta = EventMeta(fact.source, served.world.numbered(), fact.identity)

    async def run() -> None:
        served.world.cause = (fact.name, meta.seq)
        try:
            await _running.run(
                f"event:{fact.name}", served.agent.on_event, fact.name, dict(fact.data), meta
            )
        finally:
            served.world.cause = None

    served.jobs.put_nowait(run)


def synced(served: Live) -> None:
    """Send each block whose text changed since this call's last send; the tools if they moved."""
    with served.lock:
        rendered = render(served.agent, served.world.line(), remembered=served.remembered)
        for block in rendered.blocks:
            # A block never sent is empty, as the runtime starts it: an empty one costs nothing.
            if block.text == served.sent.get(block.name, ""):
                continue
            served.sent[block.name] = block.text
            served.call.set_prompt(block.name, block.text)
        visible = served.agent.visible_tools()
        shown = json.dumps([spec.written() for spec in visible])
        if shown != served.tools_shown:
            served.tools_shown = shown
            served.call.set_tools(visible)


def recalled(ops: MemoryOps) -> list[str]:
    """What a recall brought, as `remembers` reads it: each fact's text and its category."""
    return [
        word
        for op in ops.ops
        if op.op == "recall"
        for fact in op.facts
        for word in (fact.text, fact.category or "")
    ]


def jsonable(value: object) -> JsonObject:
    """A snapshot as the wire carries it: dataclasses, models and dates made JSON."""
    made: JsonObject = ANYTHING.dump_python(value, mode="json")
    return made


def as_object(data: object) -> JsonObject:
    """A log line's data is an object on the wire: anything else is put under `value`."""
    if data is None:
        return {}
    made = ANYTHING.dump_python(data, mode="json")
    return made if isinstance(made, dict) else {"value": made}  # pyright: ignore[reportUnknownVariableType]
