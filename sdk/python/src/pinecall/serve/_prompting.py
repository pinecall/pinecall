"""`serve prompt`: the class in a file, opened in the state asked for, its prompt printed."""

from typing import TextIO

from pinecall.agent import Agent
from pinecall.blocks import header_for, show_prompt
from pinecall.call import CallLine, CallWorld
from pinecall.serve._loading import Flags, load_served


def prompt(flags: Flags, out: TextIO) -> int:
    """Print the prompt a call on `flags.channel` would get, in the state the flags name."""
    cls = load_served(flags.served[0])
    instance = cls().seal()
    # A call of its own, so the channel's block is the one this channel and medium get.
    instance.serving(CallWorld(CallLine(id="", channel=flags.channel, medium=flags.medium)))
    if flags.state:
        instance.start_in(flags.state)
    out.write(show_prompt(instance) + "\n")
    if flags.show_machine:
        out.write("\n" + machine(instance) + "\n")
    return 0


def machine(instance: Agent) -> str:
    """The tools the class declares, marking the ones this state shows, under the stage."""
    stage = getattr(instance, "stage", None)
    header = header_for("tools") + ("" if stage is None else f" stage: {stage}")
    declared = getattr(type(instance), "_pinecall_tools")  # noqa: B009 - the class's own
    if not declared:
        return f"{header}\n\n  this agent declares no tools"
    shown = {spec.name for spec in instance.visible_tools()}
    width = max(len(name) for name in declared)
    lines = [
        f"  {mark(name in shown)} {name.ljust(width)}  {gated_by(one, stage, shown=name in shown)}"
        for name, one in declared.items()
    ]
    return "\n".join([header, "", *lines])


def gated_by(declared: object, stage: object, *, shown: bool) -> str:
    """What gates a tool: its stages, its `when`, or nothing; hidden in its stage, its `when`."""
    stages: tuple[str, ...] | None = getattr(declared, "stages", None)
    when = getattr(declared, "when", None)
    if stages is None:
        return "always" if when is None else "when(state)"
    named = " · ".join(stages)
    return f"{named} · when(state) says no" if not shown and stage in stages else named


def mark(shown: bool) -> str:  # noqa: FBT001 - the one fact it draws
    """● for a tool the model sees, ○ for one it does not."""
    return "●" if shown else "○"
