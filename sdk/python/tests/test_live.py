"""One served call as the bridge holds it: nothing sent yet, nobody passed it, no screen drawn."""

from pinecall import Agent, CallLine, CallWorld
from pinecall._asking import Asking
from pinecall._calls import Call
from pinecall._live import Live
from pinecall.call import nowhere


def test_a_served_call_starts_with_nothing_sent_no_pass_and_no_screen() -> None:
    call = Call("CA_1", nowhere, 0.0, nowhere)
    served = Live(Agent(), Agent, CallWorld(CallLine(id="CA_1", contact="x")), call, Asking([]))
    assert (served.sent, served.tools_shown, served.passes, served.screened.screen) == (
        {},
        None,
        0,
        None,
    )
    assert (served.team, served.rules, served.draws, served.busy) == (None, (), False, False)
