"""What a call to a number goes through now: its carrier, the fence, its env's rule, its agent."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Channel
from runtime.exceptions import PinecallError
from runtime.kit.crypto import Vault
from runtime.telephony.models import Route
from runtime.telephony.service import rebuild
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.catalog import BOX_CARRIER, KNOWN
from runtime.telephony.service.rebuild import Fencing

type StepName = Literal["carrier", "fence", "world", "agent"]
type StepState = Literal["ok", "waiting", "broken"]

# A state ranked by how much it stops a call: the worst step is what the number does.
RANK: dict[StepState, int] = {"ok": 0, "waiting": 1, "broken": 2}


@dataclass(frozen=True, slots=True)
class PathStep:
    """One step of a call's way to its agent, what it does now, and what would make it work."""

    step: StepName
    state: StepState
    says: str
    fix: str | None = None


@dataclass(frozen=True, slots=True)
class NumberPath:
    """A number's four steps, the worst of them (what a call to it does now), and when one last reached the box."""

    number: str
    steps: list[PathStep]
    rings: StepState
    last_call_at: datetime | None


# What fences the org's numbers is read once, and each step reads it from there.
async def path_of(
    session: AsyncSession, vault: Vault, http: httpx.AsyncClient, names: SipNames, route: Route, *, running: bool
) -> NumberPath:
    """The number's four steps, its carrier's API asked when it has one."""
    fencing = await rebuild.fencing_of(session, vault, route.org)
    steps = [
        await _ask_carrier_step(http, names, route, fencing),
        _fence_step(route, fencing),
        PathStep("world", "ok", f"The {route.env} rule sends it to the {route.env} fleet"),
        _agent_step(route, running=running),
    ]
    return NumberPath(route.number, steps, _worst(step.state for step in steps), route.last_call_at)


async def rings_of(
    session: AsyncSession, vault: Vault, routes: Sequence[Route], is_running: Callable[[Route], bool]
) -> list[StepState]:
    """What a call to each of one org's numbers does now, read off the tables, no carrier asked."""
    if not routes:
        return []
    fencing = await rebuild.fencing_of(session, vault, routes[0].org)
    return [
        _worst(
            step.state
            for step in (
                _carrier_step(route, pointed_by_the_box=_is_pointed(route, fencing)),
                _fence_step(route, fencing),
                _agent_step(route, running=is_running(route)),
            )
        )
        for route in routes
    ]


def _worst(states: Iterable[StepState]) -> StepState:
    found: StepState = "ok"
    for state in states:
        if RANK[state] > RANK[found]:
            found = state
    return found


# A number the box pointed here through an API is taken as pointed until a look says otherwise.
def _carrier_step(route: Route, *, pointed_by_the_box: bool) -> PathStep:
    if route.last_call_at is not None:
        return PathStep("carrier", "ok", "Calls to it reach this box")
    if route.channel is Channel.whatsapp:
        return PathStep("carrier", "waiting", "Waiting for the first message")
    if pointed_by_the_box:
        return PathStep("carrier", "ok", "Pointed at this box when it was added")
    return PathStep("carrier", "waiting", f"Waiting for the first call to {route.number}")


def _is_pointed(route: Route, fencing: Fencing) -> bool:
    account = fencing.carriers.get(route.account or "")
    return route.managed or (account is not None and account.has_api)


# The sentence names the party asked: until 2026-11 it said Twilio for any account with an API.
async def _ask_carrier_step(http: httpx.AsyncClient, names: SipNames, route: Route, fencing: Fencing) -> PathStep:
    account = fencing.carriers.get(route.account or "")
    if route.last_call_at is not None or account is None or route.channel is not Channel.phone:
        return _carrier_step(route, pointed_by_the_box=route.managed)
    try:
        pointed = await account.is_pointed_here(http, names, route.number, route.env)
    except PinecallError:
        return PathStep("carrier", "waiting", f"{account.name} did not answer: it is asked again next time")
    if pointed is None:
        return _carrier_step(route, pointed_by_the_box=route.managed)
    if pointed:
        return PathStep("carrier", "ok", f"{account.name} sends it to this box")
    return PathStep(
        "carrier",
        "broken",
        f"{account.name} does not send it to this box",
        fix=f"Add it again from your {account.name} account: it is pointed here on the way",
    )


# Until 2026-11 a network the operator refused was said to wait for him: what is not approved is
# told apart now, and a refusal says so.
def _fence_step(route: Route, fencing: Fencing) -> PathStep:
    if route.channel is Channel.whatsapp:
        return PathStep("fence", "ok", "Signed by Meta, checked on every message")
    if not route.approved:
        return PathStep(
            "fence",
            "waiting",
            "You hooked it yourself: the box's operator approves that it is yours",
            fix="The operator approves it once under Numbers",
        )
    try:
        fenced = fencing.fence_route(route)
    except PinecallError as unfenced:
        return PathStep("fence", "broken", str(unfenced))
    if fenced.orphaned:
        return PathStep(
            "fence",
            "broken",
            "The account it was imported from is gone: nothing says where its calls come from",
            fix="Bring the account again, then add the number again from it",
        )
    if fenced.fence is None and fenced.waiting:
        return PathStep(
            "fence",
            "waiting",
            f"{', '.join(fenced.waiting)} waits for the box's operator",
            fix="The operator approves it once under Carriers",
        )
    if fenced.fence is None:
        return PathStep(
            "fence",
            "broken",
            f"The box's operator refused {', '.join(fenced.refused)}",
            fix="Name the networks your PBX or carrier calls from, and add it again",
        )
    account = fencing.carriers.get(route.account or "")
    kind = route.via or BOX_CARRIER
    known = KNOWN[kind].name if not route.networks and kind in KNOWN else "your PBX"
    return PathStep("fence", "ok", f"Admitted from {known if account is None else account.name}'s networks")


def _agent_step(route: Route, *, running: bool) -> PathStep:
    if running:
        return PathStep("agent", "ok", f"{route.agent} is running")
    return PathStep(
        "agent",
        "broken",
        f"Nobody runs {route.agent} in the {route.env}",
        fix="Run pinecall start in the agent's folder, or deploy it",
    )
