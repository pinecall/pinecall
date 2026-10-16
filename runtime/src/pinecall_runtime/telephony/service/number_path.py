"""What a call to a number goes through now: its carrier, the fence, its env's rule, its agent."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import Channel
from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.telephony.schemas import StepState
from pinecall_runtime.telephony.service import accounts, networks, sip
from pinecall_runtime.telephony.service.accounts import CarrierAccount
from pinecall_runtime.telephony.service.catalog import BOX_CARRIER, KNOWN
from pinecall_runtime.telephony.service.fence import declared_networks, own_networks
from pinecall_runtime.telephony.service.records import RouteRecord
from pinecall_runtime.telephony.service.twilio import origination_uri

type Step = Literal["carrier", "fence", "world", "agent"]

# A state ranked by how much it stops a call: the worst step is what the number does.
RANK: dict[StepState, int] = {"ok": 0, "waiting": 1, "broken": 2}


@dataclass(frozen=True, slots=True)
class PathStep:
    """One step of a call's way to its agent, what it does now, and what would make it work."""

    step: Step
    state: StepState
    says: str
    fix: str | None = None


@dataclass(frozen=True, slots=True)
class NumberPath:
    """A number's four steps, and the worst of them: what a call to it does now."""

    steps: list[PathStep]
    rings: StepState


async def path_of(session: AsyncSession, handles: Handles, record: RouteRecord, *, running: bool) -> NumberPath:
    """The number's four steps, its carrier's API asked when it has one."""
    carriers, approved = await _what_fences(session, handles, record.route.org)
    carrier = carriers.get(record.route.account or "")
    steps = [
        await _carrier_step_asked(handles, record, carrier),
        _fence_step(record, carrier, approved),
        PathStep("world", "ok", f"The {record.route.env} rule sends it to the {record.route.env} fleet"),
        _agent_step(record, running=running),
    ]
    return NumberPath(steps=steps, rings=_worst(step.state for step in steps))


async def rings_of(
    session: AsyncSession,
    handles: Handles,
    records: list[RouteRecord],
    running: Callable[[RouteRecord], bool],
) -> list[StepState]:
    """What a call to each of one org's numbers does now, read off the tables, no carrier asked."""
    if not records:
        return []
    carriers, approved = await _what_fences(session, handles, records[0].route.org)
    return [
        _worst(
            step.state
            for step in (
                _carrier_step(record, pointed_by_the_box=_pointed(handles, record, carriers)),
                _fence_step(record, carriers.get(record.route.account or ""), approved),
                _agent_step(record, running=running(record)),
            )
        )
        for record in records
    ]


def _worst(states: Iterable[StepState]) -> StepState:
    found: StepState = "ok"
    for state in states:
        if RANK[state] > RANK[found]:
            found = state
    return found


async def _what_fences(
    session: AsyncSession, handles: Handles, org: str
) -> tuple[dict[str, CarrierAccount], dict[str, tuple[str, ...]]]:
    carriers = await accounts.carriers_of(session, handles.vault, org)
    return {carrier.id: carrier for carrier in carriers}, await networks.approved(session, org)


# A number the box pointed here through an API is taken as pointed until a look says otherwise.
def _carrier_step(record: RouteRecord, *, pointed_by_the_box: bool) -> PathStep:
    if record.route.last_call_at is not None:
        return PathStep("carrier", "ok", "Calls to it reach this box")
    if record.route.channel is Channel.whatsapp:
        return PathStep("carrier", "waiting", "Waiting for the first message")
    if pointed_by_the_box:
        return PathStep("carrier", "ok", "Pointed at this box when it was added")
    return PathStep("carrier", "waiting", f"Waiting for the first call to {record.route.number}")


def _pointed(handles: Handles, record: RouteRecord, carriers: dict[str, CarrierAccount]) -> bool:
    carrier = carriers.get(record.route.account or "")
    return record.route.managed or (carrier is not None and accounts.control_of(handles.http, carrier) is not None)


async def _carrier_step_asked(handles: Handles, record: RouteRecord, carrier: CarrierAccount | None) -> PathStep:
    control = None if carrier is None else accounts.control_of(handles.http, carrier)
    if record.route.last_call_at is not None or control is None or record.route.channel is not Channel.phone:
        return _carrier_step(record, pointed_by_the_box=record.route.managed)
    number = record.route.number
    here = origination_uri(sip.sip_domain_of(handles, record.route.env))
    try:
        owned = await control.number(number)
        trunk = await control.trunk_pointing_at(here)
    except PinecallError:
        return PathStep("carrier", "waiting", "Twilio did not answer: it is asked again next time")
    if owned is not None and trunk is not None and owned.trunk_sid == trunk.sid:
        return PathStep("carrier", "ok", "Twilio sends it to this box")
    return PathStep(
        "carrier",
        "broken",
        "Twilio does not send it to this box",
        fix="Add it again from your Twilio account: it is pointed here on the way",
    )


def _fence_step(record: RouteRecord, carrier: CarrierAccount | None, approved: dict[str, tuple[str, ...]]) -> PathStep:
    route = record.route
    if route.channel is Channel.whatsapp:
        return PathStep("fence", "ok", "Signed by Meta, checked on every message")
    if not route.approved:
        return PathStep(
            "fence",
            "waiting",
            "You hooked it yourself: the box's operator approves that it is yours",
            fix="The operator approves it once under Numbers",
        )
    declared = (tuple(route.networks) or None) if carrier is None else declared_networks(carrier)
    source = route.number if carrier is None else carrier.id
    own, waiting = own_networks(declared, approved.get(source, ()))
    if sip.fence_now(record, carrier, approved) is None:
        return PathStep(
            "fence",
            "waiting",
            f"{', '.join(waiting)} waits for the box's operator",
            fix="The operator approves it once under Carriers",
        )
    kind = route.via or BOX_CARRIER
    who = KNOWN[kind].name if own is None and kind in KNOWN else "your PBX"
    return PathStep("fence", "ok", f"Admitted from {who}'s networks")


def _agent_step(record: RouteRecord, *, running: bool) -> PathStep:
    agent, env = record.route.agent, record.route.env
    if running:
        return PathStep("agent", "ok", f"{agent} is running")
    return PathStep(
        "agent",
        "broken",
        f"Nobody runs {agent} in the {env}",
        fix="Run pinecall start in the agent's folder, or deploy it",
    )
