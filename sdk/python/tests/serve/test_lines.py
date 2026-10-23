"""What serve prints: the wire entry a line for the CLI, and where a drain left the calls."""

import io
import json

from pinecall.client import Client, Drained
from pinecall.serve._lines import drain_line, entry_line, said
from pinecall.wire.frames import Entry
from tests.fakes.gateway import KEY, FakeGateway


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


async def test_an_agent_an_admin_killed_is_one_line_on_err_and_the_wire_goes_on_out(
    gateway: FakeGateway,
) -> None:
    client = Client(gateway.url, KEY)
    client.agent("clinica")
    out, err = io.StringIO(), io.StringIO()
    printer = said(client, out, err, {}, events=True)
    await client.connect()
    await gateway.kill("clinica", "clinica was killed by Ana")
    await gateway.until(lambda: "killed" in err.getvalue())
    printer.close()
    await client.close()
    assert err.getvalue() == "clinica  ✗ clinica was killed by Ana\n"
    assert "was killed by Ana" in out.getvalue()
