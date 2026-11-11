"""What a newborn org is given: its quotas in each env, for a person's first org and for any later one."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.billing.service.quotas import QUOTA_NAMES, Quotas, put_quotas
from runtime.enums import Env
from runtime.platform import service as platform


@dataclass(frozen=True, slots=True)
class Admission:
    """What a newborn org may use in each env: a person's first org, and any later one."""

    first: Mapping[Env, Quotas] = field(default_factory=dict[Env, Quotas])
    # None gives a later org what the first got; set, one trial per person.
    later: Mapping[Env, Quotas] | None = None

    def quotas_for(self, *, already: int) -> Mapping[Env, Quotas]:
        """The quotas of a newborn org whose person has `already` this many orgs."""
        return self.first if self.later is None or already == 0 else self.later


# The row keeps the shape it always had: each env's quotas flat, `lends` a sorted list or null.
def _load_quotas(value: Mapping[str, Any]) -> Quotas:
    lends = value.get("lends")
    return Quotas.of_limits(
        {name: value.get(name) for name in QUOTA_NAMES},
        lends=None if lends is None else frozenset(lends),
        simulations_at_once=value.get("simulations_at_once"),
        comparison_calls=value.get("comparison_calls"),
    )


def _dump_quotas(quotas: Quotas) -> dict[str, Any]:
    kept: dict[str, Any] = dict(quotas.limits.items())
    kept["lends"] = None if quotas.lends is None else sorted(quotas.lends)
    kept["simulations_at_once"] = quotas.simulations_at_once
    kept["comparison_calls"] = quotas.comparison_calls
    return kept


def _load_envs(value: Mapping[str, Any]) -> dict[Env, Quotas]:
    return {Env(env): _load_quotas(quotas) for env, quotas in value.items()}


# One mapper for the row and for the operator's body: the two are the same JSON by design.
def load_admission(value: Mapping[str, Any]) -> Admission:
    """The admission a JSON value says."""
    later = value.get("later")
    return Admission(first=_load_envs(value.get("first") or {}), later=None if later is None else _load_envs(later))


def dump_admission(admission: Admission) -> dict[str, Any]:
    """The admission as the JSON the box keeps and the operator reads."""
    later = admission.later
    return {
        "first": {env.value: _dump_quotas(quotas) for env, quotas in admission.first.items()},
        "later": None if later is None else {env.value: _dump_quotas(quotas) for env, quotas in later.items()},
    }


ADMISSION: platform.Setting[Admission] = platform.Setting("admission", load_admission, dump_admission)


async def get_admission(session: AsyncSession) -> Admission:
    """What a newborn org is given; nothing limited on a box that never said."""
    return await platform.find_setting(session, ADMISSION) or Admission()


async def put_admission(session: AsyncSession, admission: Admission) -> None:
    """Replace what a newborn org is given, whole."""
    await platform.put_setting(session, ADMISSION, admission)


# Read at the moment an org is made: the orgs already made keep their quotas.
async def give_first_quotas(session: AsyncSession, org: str, *, already: int) -> None:
    """Set a newborn org's quotas in each env, as the box's admission says for its person."""
    admission = await get_admission(session)
    for env, quotas in admission.quotas_for(already=already).items():
        await put_quotas(session, org, env, quotas)
