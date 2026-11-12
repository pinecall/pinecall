"""The judge judged: calls a person labelled, and each judge's agreement with those labels."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.enums import Env, JudgeAnswer
from runtime.evals.models import JudgeLabel
from runtime.evals.repository import LabelRepository
from runtime.exceptions import Conflict
from runtime.judging import service as judging

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


@dataclass(frozen=True, slots=True)
class Agreement:
    """One judge against the labels people gave: how many, compared, agreed, and whether it is trusted."""

    judge: str
    labelled: int
    compared: int
    agreed: int
    rate: float | None
    # None until enough labels were compared to say; False is a judge under its line.
    trusted: bool | None


@dataclass(frozen=True, slots=True)
class Calibration:
    """Each judge's agreement with the labels, and the line it is held to."""

    judges: list[Agreement]
    labels_to_judge: int = LABELS_TO_JUDGE
    agrees_at_least: float = AGREES_AT_LEAST


# A label for a judge nobody wrote would stay in the listing for ever: no endpoint removes one.
async def check_labellable(session: AsyncSession, where: Where, judge: str) -> None:
    """Refuse a label for a judge the agent's calls never meet (404), or one that answers no verdict (409)."""
    declaration = await agents.declaration_of(session, Scope(where.org, where.env), where.agent)
    class_judges = None if declaration is None else declaration.judges
    spec = await judging.judge_named(session, where.org, where.agent, judge, class_judges)
    if spec.answer is not JudgeAnswer.verdict:
        raise Conflict(
            f"{judge} answers a {spec.answer.value}, not held or broken: a label says whether a judge should "
            "have held, so only a judge that answers a verdict takes one"
        )


async def label_call(session: AsyncSession, where: Where, label: Label) -> None:
    """Keep what one judge should have answered on a call, replacing the label before it for that call and judge."""
    await check_labellable(session, where, label.judge)
    await LabelRepository(session).put(
        JudgeLabel(
            call=label.call,
            judge=label.judge,
            org=where.org,
            env=where.env,
            agent=where.agent,
            held=label.held,
            note=label.note,
            author=label.author,
        )
    )


async def calibration_of(session: AsyncSession, org: str, env: Env, agent: str | None) -> Calibration:
    """Each judge against the labels on the org's calls in the env, one agent's or all."""
    rows = await LabelRepository(session).measure_agreement(org, env, agent)
    return Calibration(
        [
            Agreement(
                judge=row.judge,
                labelled=row.labelled,
                compared=row.compared,
                agreed=row.agreed,
                rate=_rate(row.agreed, row.compared),
                trusted=_is_trusted(row.agreed, row.compared),
            )
            for row in rows
        ]
    )


def _rate(agreed: int, compared: int) -> float | None:
    return agreed / compared if compared else None


def _is_trusted(agreed: int, compared: int) -> bool | None:
    rate = _rate(agreed, compared)
    if compared < LABELS_TO_JUDGE or rate is None:
        return None
    return rate >= AGREES_AT_LEAST
