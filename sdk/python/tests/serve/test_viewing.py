"""`view.render`: the class's panel for a conversation, or the refusal with its status."""

from pathlib import Path

import pytest

from pinecall import Agent, DevRefused
from pinecall.serve._loading import Served, load_served
from pinecall.serve._viewing import ONLY_THE_VIEW, answered
from tests.fakes.project import written


async def test_a_panel_is_drawn_for_the_conversation_asked(tmp_path: Path) -> None:
    cls = load_served(Served(written(tmp_path), "recepcion"))
    panel = await answered(cls, "recepcion", "view.render", {"contact": "+34600", "call": "CA_1"})
    assert panel == {"name": "Ficha", "nodes": [{"tag": "text", "text": "+34600 en CA_1"}]}


async def test_every_other_verb_is_the_clis_and_a_panel_asked_without_a_call_is_refused(
    tmp_path: Path,
) -> None:
    cls = load_served(Served(written(tmp_path), "recepcion"))
    with pytest.raises(DevRefused, match=ONLY_THE_VIEW):
        await answered(cls, "recepcion", "goldens.roster", {})
    with pytest.raises(DevRefused) as refused:
        await answered(cls, "recepcion", "view.render", {"contact": "+34600"})
    assert (refused.value.status, refused.value.detail) == (
        422,
        "call is a name, and it was missing",
    )


async def test_a_class_with_no_panel_and_one_whose_panel_fails_say_so() -> None:
    class Callada(Agent):
        """Sin panel."""

    with pytest.raises(DevRefused, match="callada declares no view") as refused:
        await answered(Callada, "callada", "view.render", {"contact": "c", "call": "CA"})
    assert refused.value.status == 404
