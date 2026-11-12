"""A session built for a written call: the model alone, the turn taken by hand."""

from livekit.agents.voice import AgentSession

from runtime.enums import Stage
from runtime.providers import service as providers
from runtime.providers.stage import Running
from runtime.session.call import Call
from runtime.session.hearing import policy_for
from runtime.session.line import Line
from runtime.session.lookups import TEXT_LOOKUP_MS, Lookups
from runtime.session.session import TOOL_STEPS, OnEnded, Place, Session
from runtime.session.stages import write_switches


# A written call has no ears and no voice, so its text is neither paced nor billed as speech;
# its turns are taken by hand, one message at a time (`Session.hear`).
def text_session(
    call: Call,
    thinking: Running,
    place: Place,
    *,
    lookup_budget_ms: int | None = None,
    tool_steps: int | None = None,
    on_ended: OnEnded | None = None,
) -> Session:
    """A written call: the same session with the model alone, in a room or in none."""
    model = providers.build_thinking(thinking)
    write_switches(call.writing, (model,))
    live: AgentSession[Call] = AgentSession(
        userdata=call,
        llm=model,
        turn_handling={"turn_detection": "manual", "preemptive_generation": {"enabled": False}},
        max_tool_steps=tool_steps or TOOL_STEPS,
    )
    return Session(
        live,
        (model,),
        Lookups(call, lookup_budget_ms or TEXT_LOOKUP_MS),
        Line(call, live, place.melody),
        policy_for(call.declaration.language, call.declaration.turn),
        running={Stage.llm: thinking},
        place=place,
        on_ended=on_ended,
    )
