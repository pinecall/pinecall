"""An org's limits as a model: counts never negative, reached at the limit, one list of names."""

import typing

import pytest

from runtime.billing import service as billing
from runtime.billing.service import quotas
from runtime.exceptions import ValidationError
from runtime.wire.parts import QuotaName

# ── the limits, as a model ──


def test_a_quota_is_a_count_and_never_negative() -> None:
    """A negative limit is refused when the quotas are made."""
    with pytest.raises(ValidationError, match="minutes cannot be -1"):
        billing.Quotas(minutes=-1)


def test_a_limit_is_reached_at_it_and_a_push_refused_only_past_it() -> None:
    """Using the limit reaches it; a push sized up front may fill it and not pass it."""
    quotas = billing.Quotas(messages=3, knowledge_chunks=10)
    assert quotas.limit_reached("messages", 2) is None
    assert quotas.limit_reached("messages", 3) == 3
    assert quotas.limit_exceeded("knowledge_chunks", 10) is None
    assert quotas.limit_exceeded("knowledge_chunks", 11) == 10


# One list of the quotas' names: the wire's literal, the tuple the limits page walks, and the fields
# of `Quotas` that are limits. A quota added to one and not the others was a limit nobody could read.
def test_the_quotas_names_are_one_list_in_the_wire_the_tuple_and_the_model() -> None:
    assert set(quotas.QUOTA_NAMES) == set(typing.get_args(QuotaName.__value__))
    assert len(quotas.QUOTA_NAMES) == len(set(quotas.QUOTA_NAMES))
    assert set(billing.Quotas().limits) == set(quotas.QUOTA_NAMES)


def test_a_quota_of_zero_switches_the_feature_off_and_none_is_unlimited() -> None:
    """Zero means not in the plan; no limit means as much as the org likes."""
    quotas = billing.Quotas(simulations=0)
    assert quotas.is_switched_off("simulations")
    assert not quotas.is_switched_off("minutes")
    assert quotas.limit_reached("minutes", 10**9) is None


# How simulations are shaped is not a month's count: nobody having set it is the platform's own
# number, never no limit, since each simulated call on the line is a seat of the fleet.
def test_an_org_nobody_gave_more_simulates_at_the_platforms_own_numbers() -> None:
    """Unset, the calls at once and the calls a comparison places are the platform's; set, the org's."""
    unset = billing.Quotas()
    assert unset.simulating_at_most == quotas.SIMULATIONS_AT_ONCE
    assert unset.compared_at_most == quotas.COMPARISON_CALLS
    given = billing.Quotas(simulations_at_once=25, comparison_calls=60)
    assert (given.simulating_at_most, given.compared_at_most) == (25, 60)
    assert billing.Quotas(simulations_at_once=0).simulating_at_most == 0


def test_a_negative_shape_is_refused_as_a_negative_quota_is() -> None:
    """The calls at once and the calls a comparison places are counts too."""
    with pytest.raises(ValidationError):
        billing.Quotas(comparison_calls=-1)
