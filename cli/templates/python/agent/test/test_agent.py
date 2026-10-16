"""Ring 0: the class as software — no network, no key, no model."""

from pathlib import Path

from pinecall import Agent, CallLine, CallWorld, render
from pinecall.testing import load

# A folder named by a slug cannot be imported: the class is loaded as `pinecall start` loads it.
AGENT = load(Path(__file__).parents[1] / "agent.py")


def serving() -> Agent:
    agent = AGENT().seal()
    return agent.serving(CallWorld(CallLine(id="CA_1", contact="+15550100", channel="phone")))


def test_until_there_is_a_message_the_view_asks_for_one() -> None:
    assert "ask for their name and what the call is about" in render(serving())["view"]


def test_a_message_taken_ends_the_call_with_it() -> None:
    agent = serving()
    agent.run_tool("take_message", {"name": "Ana", "about": "a refund"})

    assert agent.snapshot()["stage"] == "done"
    assert "Ana, about a refund" in render(agent)["view"]
