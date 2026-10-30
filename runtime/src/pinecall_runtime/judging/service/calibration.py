"""The judge judged: calls a person labelled, and each judge's agreement with those labels."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.service import declarations
from pinecall_runtime.enums import Env, JudgeAnswer
from pinecall_runtime.exceptions import Conflict
from pinecall_runtime.judging.repository import LabelRepository
from pinecall_runtime.judging.schemas import Calibration, JudgeAgreement
from pinecall_runtime.judging.service.judges import judge_named
from pinecall_runtime.kit.auth import Scope

# A judge is judged once this many of its verdicts have a label beside them, and trusted while it
# agrees with at least this share of them; under its line it is reported, never dropped silently.
LABELS_TO_JUDGE = 10
AGREES_AT_LEAST = 0.8
NOT_A_VERDICT = (
    "{judge} answers a {answer}, not held or broken: a label says whether a judge should have held, "
    "so only a judge that answers a verdict takes one"
)


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


# A label for a judge nobody wrote would stay in the listing for ever: no endpoint removes one.
async def check_labellable(session: AsyncSession, where: Where, judge: str) -> None:
    """Refuse a label for a judge the agent's calls never meet (404), or one that answers no verdict (409)."""
    declared = await declarations.declared_in(session, Scope(where.org, where.env), where.agent)
    spec = await judge_named(session, where.org, where.agent, judge, None if declared is None else declared.judges)
    if spec.answer is not JudgeAnswer.verdict:
        raise Conflict(NOT_A_VERDICT.format(judge=judge, answer=spec.answer.value))


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
