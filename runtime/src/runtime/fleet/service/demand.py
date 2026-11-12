"""How many scaled workers a fleet wants: the rule Kubernetes sizes the burst by, and the floor it keeps warm."""

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from fractions import Fraction
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Env
from runtime.fleet.service import envs, slots
from runtime.fleet.service.roster import Roster
from runtime.platform import service as platform
from runtime.wire.signal import WorkerStatus

logger = logging.getLogger(__name__)

# The most scaled workers a fleet is ever asked for when whoever asks names no ceiling.
AT_MOST = 10


@dataclass(frozen=True, slots=True)
class Line:
    """Where a fleet is kept: the busy target, the slack under it, how many, and their slots."""

    # Grow above `target`; shrink only below `target - slack`, so two asks do not oscillate.
    target: float = 0.6
    slack: float = 0.15
    at_least: int = 0
    at_most: int = AT_MOST
    # PINECALL_MAX_JOBS of a scaled worker: what one more of them adds.
    slots_per_worker: int = 4


@dataclass(frozen=True, slots=True)
class Demand:
    """What the fleet wants now, and why: its calls and the slots it holds."""

    fleet: str
    wanted: int
    active: int
    slots: int


# Until 2026-11 the floor was `min` in the chart's values, held by the autoscaler: changing it was a
# release of the chart, and going back a release undid it without a word. It is a fact of the fleet
# now, set by the operator and counted here, so the one number Kubernetes reads already holds it.
@dataclass(frozen=True, slots=True)
class Floors:
    """The scaled workers each env's fleet keeps warm whatever its calls: none unless the operator said."""

    production: int = 0
    sandbox: int = 0

    def of(self, env: Env) -> int:
        """The floor of the env's fleet."""
        return self.production if env is Env.production else self.sandbox


def _load(value: Mapping[str, Any]) -> Floors:
    return Floors(production=int(value.get("production") or 0), sandbox=int(value.get("sandbox") or 0))


FLOORS: platform.Setting[Floors] = platform.Setting("fleet_floors", _load, asdict)


async def get_floors(session: AsyncSession) -> Floors:
    """The workers each env's fleet keeps warm; none where the operator set no floor."""
    return await platform.find_setting(session, FLOORS) or Floors()


# The floor is in no repository any more: a floor of one is a node that never stops, and this line
# is the record of who asked for it.
async def put_floors(session: AsyncSession, floors: Floors, *, by: str) -> None:
    """Set each env's floor, whole; the autoscaler's next ask reads it."""
    await platform.put_setting(session, FLOORS, floors)
    logger.info(
        "the fleets' floors of warm workers are now %d in production and %d in the sandbox, set by %s",
        floors.production,
        floors.sandbox,
        by,
    )


# A cluster's workers that scale (their names start with `scaled`) are sized by Kubernetes, which
# asks this number, counting the slots of the workers that do not scale (a core node's) first, so
# a call they hold asks for no scaled one. Grow to what brings busy under the target, and never
# under the floor; let one go only when busy stays under target - slack without it; else hold.
# Absolute, so a pod still booting, not yet heard, is never asked for twice. The ceiling is the
# pool's own, so a floor set over it asks for the ceiling.
def demand_of(fleet: str, workers: Sequence[WorkerStatus], scaled: str, line: Line, now: float) -> Demand:
    """How many scaled workers the fleet wants now, its calls, and the slots it holds."""
    counted = [worker for worker in workers if slots.is_heard(worker, now) and worker.max_jobs is not None]
    holding = [worker for worker in counted if not worker.cordoned]
    active = sum(worker.active for worker in counted)
    fixed = sum(worker.max_jobs or 0 for worker in holding if not worker.worker.startswith(scaled))
    current = sum(1 for worker in holding if worker.worker.startswith(scaled))
    each = line.slots_per_worker
    # The target's decimal as written: 6 / 0.6 in floats is 10.000000000000002, one slot too many.
    needed = math.ceil(Fraction(active) / Fraction(str(line.target))) - fixed
    for_the_calls = max(0, math.ceil(Fraction(needed) / each)) if needed > 0 else 0
    grown = max(for_the_calls, line.at_least)
    capacity = fixed + current * each
    if grown > current:
        return Demand(fleet, min(grown, line.at_most), active, capacity)
    left = fixed + (current - 1) * each
    # With no call one may always go; with calls, only if the slots left keep busy under the slack.
    quiet = active == 0 or (left > 0 and active / left < line.target - line.slack)
    if current > grown and quiet:
        return Demand(fleet, current - 1, active, capacity)
    return Demand(fleet, current, active, capacity)


async def demand_of_env(session: AsyncSession, roster: Roster, env: Env, scaled: str, line: Line, now: float) -> Demand:
    """What the env's fleet wants of its scaled workers now, its floor counted."""
    fleet = await envs.fleet_of_env(session, env)
    floor = (await get_floors(session)).of(env)
    return demand_of(fleet, roster.workers_of(fleet, now), scaled, replace(line, at_least=floor), now)
