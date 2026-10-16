"""What serve prints: the wire entry a line for the CLI, and where a drain left the calls."""

import json

from pinecall.client import Drained
from pinecall.serve._lines import drain_line, entry_line
from pinecall.wire.frames import Entry


def test_an_entry_is_one_line_of_its_type_agent_call_and_data_as_the_gateway_wrote_it() -> None:
    entry = Entry(
        seq=3,
        ts=1.0,
        call=None,
        agent="clinica",
        type="agent.registered",
        ephemeral=False,
        data={"app": "app_1"},
    )
    assert json.loads(entry_line(entry)) == {
        "type": "agent.registered",
        "agent": "clinica",
        "call": None,
        "data": {"app": "app_1"},
    }


def test_a_drain_says_where_the_calls_went_and_what_became_of_the_tools() -> None:
    assert drain_line(Drained(0, 0, 0, 0)) == "draining · no live calls"
    assert drain_line(Drained(2, 1, 3, 2)) == (
        "draining · 2 live calls handed over · 1 live call kept for the next process"
        " · 2 tools finished · 1 tool cut"
    )
