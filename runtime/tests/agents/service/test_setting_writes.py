"""A write of the settings: a model alone rides the vendor the agent runs now, and a clear counts as a change."""

import pytest

from runtime.agents.declaration import Agent, Declaration
from runtime.agents.service.setting_names import SetByTheClass, refuse_what_the_class_sets
from runtime.agents.service.setting_writes import _changes, _name_the_vendor_in_use
from runtime.agents.settings import AgentSettings
from tests.fakes.acme import ACME


def test_a_model_alone_is_kept_on_the_vendor_the_agent_runs_now() -> None:
    """`--llm acme-2` after `acme/acme-1` is stored as `acme/acme-2`; a vendor named stays as typed."""
    before = AgentSettings(llm=f"{ACME}/acme-1", judge=f"{ACME}/acme-judge")
    assert _name_the_vendor_in_use(AgentSettings(llm="acme-2", judge="acme-3"), before) == AgentSettings(
        llm=f"{ACME}/acme-2", judge=f"{ACME}/acme-3"
    )
    assert _name_the_vendor_in_use(AgentSettings(llm="other/m"), before).llm == "other/m"


def test_a_model_alone_with_no_vendor_set_before_is_left_for_the_class_or_the_default() -> None:
    assert _name_the_vendor_in_use(AgentSettings(llm="acme-2"), AgentSettings()).llm == "acme-2"


def test_a_clear_of_a_setting_the_class_fixes_is_refused_like_a_set() -> None:
    """The body is the settings whole: a setting left out of it is one taken out, and the class's are not."""
    newest = AgentSettings(voice="v-1", llm=f"{ACME}/acme-1")
    cleared = AgentSettings(llm=f"{ACME}/acme-1")
    changed = [name for name in ("voice", "llm") if _changes(cleared, newest, name)]
    assert changed == ["voice"]
    declared = Agent("kala", Declaration(slug="kala", fixed=frozenset({"voice"})))
    with pytest.raises(SetByTheClass):
        refuse_what_the_class_sets(declared, changed)
