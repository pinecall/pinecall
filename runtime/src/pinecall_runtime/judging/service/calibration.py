"""The judge judged: calls a person labelled, and each judge's agreement with those labels."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import Env
from pinecall_runtime.judging.repository import LabelRepository
from pinecall_runtime.judging.schemas import Calibration, JudgeAgreement

# A judge is judged once this many of its verdicts have a label beside them, and trusted while it
# agrees with at least this share of them; under its line it is reported, never dropped silently.
LABELS_TO_JUDGE = 10
AGREES_AT_LEAST = 0.8


@dataclass(frozen=True, slots=True)
class Label:
    """What a person said one judge should have answered on one call, and who said it."""

    call: str
    judge: str
    held: bool
    author: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Where:
    """Whose calls a label is on: the org, the env, the agent."""

    org: str
    env: Env
    agent: str


async def label_call(session: AsyncSession, where: Where, label: Label) -> None:
    """Keep the label, replacing the one before it for the same call and judge."""
    await LabelRepository(session).put(
        call=label.call,
        judge=label.judge,
        org=where.org,
        env=where.env,
        agent=where.agent,
        held=label.held,
        note=label.note,
        author=label.author,
    )


async def calibration_of(session: AsyncSession, org: str, env: Env, agent: str | None) -> Calibration:
    """Each judge against the labels on the org's calls in the env, one agent's or all."""
    rows = await LabelRepository(session).agreement(org, env, agent)
    judges = [
        JudgeAgreement(
            judge=row.judge,
            labelled=row.labelled,
            compared=row.compared,
            agreed=row.agreed,
            rate=_rate(row.agreed, row.compared),
            trusted=_trusted(row.agreed, row.compared),
        )
        for row in rows
    ]
    return Calibration(judges=judges, labels_to_judge=LABELS_TO_JUDGE, agrees_at_least=AGREES_AT_LEAST)


def _rate(agreed: int, compared: int) -> float | None:
    return agreed / compared if compared else None


def _trusted(agreed: int, compared: int) -> bool | None:
    rate = _rate(agreed, compared)
    if compared < LABELS_TO_JUDGE or rate is None:
        return None
    return rate >= AGREES_AT_LEAST
