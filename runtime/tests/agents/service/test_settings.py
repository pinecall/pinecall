"""A write of the settings: a model alone rides the corner's vendor, and a clear counts as a change."""

import pytest

from pinecall_runtime.agents.declaration import AgentConfig, Model, Tuning
from pinecall_runtime.agents.service.settings import (
    SetByTheClass,
    _changes,
    _on_the_vendor_in_use,
    refuse_what_the_class_sets,
)
from tests.fakes.acme import ACME


def test_a_model_alone_is_kept_on_the_vendor_the_corner_runs_now() -> None:
    """`--llm acme-2` after `acme/acme-1` is stored as `acme/acme-2`; a vendor named stays as typed."""
    before = Tuning(llm=f"{ACME}/acme-1", judge=f"{ACME}/acme-judge")
    assert _on_the_vendor_in_use(Tuning(llm="acme-2", judge="acme-3"), before) == Tuning(
        llm=f"{ACME}/acme-2", judge=f"{ACME}/acme-3"
    )
    assert _on_the_vendor_in_use(Tuning(llm="other/m"), before).llm == "other/m"


def test_a_model_alone_with_no_vendor_set_before_is_left_for_the_class_or_the_default() -> None:
    assert _on_the_vendor_in_use(Tuning(llm="acme-2"), Tuning()).llm == "acme-2"


def test_a_clear_of_a_knob_the_class_fixes_is_refused_like_a_set() -> None:
    """The body is the corner whole: a knob left out of it is one taken out, and the class's are not."""
    newest = Tuning(voice="v-1", llm=f"{ACME}/acme-1")
    cleared = Tuning(llm=f"{ACME}/acme-1")
    changed = [knob for knob in ("voice", "llm") if _changes(cleared, newest, knob)]
    assert changed == ["voice"]
    declared = AgentConfig(slug="kala", voice=None, llm=Model(ACME, "acme-1"), fixed=frozenset({"voice"}))
    with pytest.raises(SetByTheClass):
        refuse_what_the_class_sets(declared, "kala", changed)
