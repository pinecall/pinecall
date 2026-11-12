"""What a tool call does on a served call, and one agent of a team taking the call from another."""

from collections.abc import Awaitable, Callable, Mapping

from pinecall import _author, _running, _tools
from pinecall._calls import Call
from pinecall._failures import hooked
from pinecall._handoff import MOST_PASSES, PASSED, mate_named, transfers_of
from pinecall._live import Live
from pinecall._screened import scene_chosen
from pinecall._sending import ANYTHING, as_object, state_of, synced
from pinecall.agent import Agent
from pinecall.errors import ToolFailed
from pinecall.screen import SHOW_SCREEN
from pinecall.wire._names import JsonObject

Ran = Callable[[JsonObject, Call], Awaitable[object]]


def runner(live: Mapping[str, Live], name: str) -> Ran:
    """What runs one tool for a call: on whatever serves it now, its answer made JSON."""

    async def ran(arguments: JsonObject, call: Call) -> object:
        served = live.get(call.id)
        if served is None:
            raise ToolFailed(f"{name}: this call is no longer being served")
        try:
            return ANYTHING.dump_python(await dispatched(served, name, arguments), mode="json")
        finally:
            if live.get(call.id) is served:
                synced(served)

    return ran


async def dispatched(served: Live, name: str, arguments: JsonObject) -> object:
    """A task given, the screen moved, the call passed, or one of the agent's own tools run."""
    if served.asking.gives(name):
        return await served.asking.given(name, arguments)
    if name == SHOW_SCREEN:
        return scene_chosen(served.world, served.screened, served.cls, arguments.get("scene"))
    registry: dict[str, _tools.Declared] = getattr(served.cls, "_pinecall_tools")  # noqa: B009 - the class's own
    declared = registry.get(name)
    if declared is None and served.team is not None:
        mate = mate_named(name, served.team)
        if mate is not None:
            return await served.world.handoff(mate, arguments)
    if declared is None:
        raise ToolFailed(f"{name}: this agent declares no such tool")
    found = declared
    return await served.asking.run(name, lambda: showing(served, found, arguments))


async def showing(served: Live, declared: _tools.Declared, arguments: JsonObject) -> object:
    """Run a tool; one that shows a scene keeps it through the turn, and puts it up once done."""
    if declared.shows is not None:
        served.screened.kept = True
    result = await _tools.run(served.agent, declared, arguments)
    if declared.shows is not None:
        served.world.scene = declared.shows
    return result


def become(served: Live, cls: type[Agent], agent: Agent | None = None) -> None:
    """The call is served by an instance of `cls` from now on; the call itself stays."""
    agent = agent or cls().seal()
    if served.last is not None:
        agent.reads_last_from(served.last)
    served.agent, served.cls = agent.serving(served.world), cls
    if served.team is not None:
        served.transfers = transfers_of(cls, served.team)
    served.stops["log"] = agent.on_log(
        lambda line: served.call.log(line.name, as_object(line.data))
    )


async def passed(
    served: Live, to: type, data: Mapping[str, object], follow: Callable[[Live], None]
) -> str:
    """One agent of the team takes the call from another; the model is told whose it is now."""
    team = served.team
    slug = None if team is None else team.get(to)
    if team is None or slug is None or not issubclass(to, Agent):
        raise ToolFailed(f"{to.__name__} is not of this call's team")
    if served.passes >= MOST_PASSES:
        raise ToolFailed(f"this call was passed {MOST_PASSES} times already: answer it yourself")
    for kind in ("state", "entries", "log"):
        served.stops.pop(kind, lambda: None)()
    served.agent.serving(None)
    served.call.log(PASSED, {"from": team.get(served.cls, ""), "to": slug, **as_object(dict(data))})
    served.world.handed, served.world.scene = dict(data), None
    become(served, to)
    served.passes += 1
    running = _running.run(_author.hook("on_call"), served.agent.on_call, served.world)
    await hooked(served.call, "on_call", running)
    served.call.set_state(state_of(served))
    synced(served)
    follow(served)
    return passed_to(slug)


# What the model reads once the call is the teammate's. It called a tool named for a transfer, and a
# small model goes on as whoever transfers ("one moment while I connect you") and then waits: so the
# words say there is nobody left to connect the caller to, and to answer them now.
def passed_to(slug: str) -> str:
    """The transfer tool's result: the call is the teammate's, and the caller waits for it."""
    return (
        f"Done: you are {slug} now, and the caller is already talking to you. "
        'There is nobody left to connect them to, so never say "one moment" '
        "or that you are connecting or transferring them. "
        f"Reply to their last message now, as {slug}."
    )
