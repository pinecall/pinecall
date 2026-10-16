"""The judge judged: labels kept once per call and judge, and each judge's agreement with them."""

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.calls.models.drift import DriftCall
from pinecall_runtime.enums import Env
from pinecall_runtime.judging.schemas import JudgeAgreement
from pinecall_runtime.judging.service.calibration import LABELS_TO_JUDGE, Label, Where, calibration_of, label_call
from tests.conftest import Tenant, needs_the_database

AGENT = "recepcion"


def counted(org: str, call: str, *, held: bool) -> DriftCall:
    """A sealed call whose judge `grounded` held or broke, as the seal counted it."""
    return DriftCall(
        call=call,
        org=org,
        env=Env.sandbox,
        holder="",
        agent=AGENT,
        day=date(2026, 9, 30),
        config_version=0,
        verdicts=[{"judge": "grounded", "criteria": "c", "held": held}],
    )


async def judged(
    sessions: async_sessionmaker[AsyncSession], org: str, env: Env, agent: str | None
) -> list[JudgeAgreement]:
    """Each judge's agreement with the labels."""
    async with sessions() as session:
        return (await calibration_of(session, org, env, agent)).judges


@needs_the_database
async def test_a_judge_is_judged_once_enough_labels_sit_beside_its_verdicts(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Seven of ten agree: judged, not trusted; relabelled, trusted. A label of no call counts, never compared."""
    where = Where(tenant.org, Env.sandbox, AGENT)
    calls = [f"call_{uuid.uuid4().hex}" for _ in range(LABELS_TO_JUDGE)]
    async with sessions.begin() as session:
        session.add_all(counted(tenant.org, call, held=True) for call in calls)
    async with sessions.begin() as session:
        for at, call in enumerate(calls):
            await label_call(session, where, Label(call, "grounded", held=at < 7, author="ana"))
        await label_call(session, where, Label("never_sealed", "grounded", held=True, author="ana"))
    (first,) = await judged(sessions, tenant.org, Env.sandbox, None)
    assert (first.labelled, first.compared, first.agreed, first.rate, first.trusted) == (11, 10, 7, 0.7, False)
    async with sessions.begin() as session:
        for call in calls[7:]:
            await label_call(session, where, Label(call, "grounded", held=True, author="bea"))
    (again,) = await judged(sessions, tenant.org, Env.sandbox, AGENT)
    assert (again.labelled, again.agreed, again.trusted) == (11, 10, True)
    assert await judged(sessions, tenant.org, Env.production, None) == []


@needs_the_database
async def test_a_judge_with_too_few_labels_compared_is_neither_trusted_nor_not(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """Under the line it is reported, never dropped and never called trusted."""
    where = Where(tenant.org, Env.sandbox, AGENT)
    call = f"call_{uuid.uuid4().hex}"
    async with sessions.begin() as session:
        session.add(counted(tenant.org, call, held=True))
    async with sessions.begin() as session:
        await label_call(session, where, Label(call, "grounded", held=False, author="ana"))
    (few,) = await judged(sessions, tenant.org, Env.sandbox, AGENT)
    assert (few.compared, few.agreed, few.rate, few.trusted) == (1, 0, 0.0, None)
