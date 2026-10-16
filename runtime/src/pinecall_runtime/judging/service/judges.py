"""The judges an org writes, the org's and one agent's own, and which of the library's it runs."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.exceptions import Conflict, NotFound
from pinecall_runtime.judging.models import AgentJudge
from pinecall_runtime.judging.repository import JudgeRepository, JudgeSwitchRepository
from pinecall_runtime.judging.schemas import JudgeRequest, JudgeRow
from pinecall_runtime.judging.service import catalog
from pinecall_runtime.judging.service.specs import JudgeSpec
from pinecall_runtime.kit.auth import THE_ORGS_OWN

PINECALL = "pinecall"
THE_ORG = "org"
NOBODY = "{whose} has no judge called {name}"
TAKEN = "{name} is {whose} judge already: one name asks one question of a call"
ONLY_ON = (
    '{name} is one of Pinecall\'s judges: only whether it runs is written, as {{"on": true}} or '
    '{{"on": false}}; a question of your own takes a name of your own'
)
NOT_A_SWITCH = "{name} is a judge of your own: it runs while it is written, and DELETE stops it"
NOT_YOURS = '{name} is one of Pinecall\'s judges and is never deleted: PUT {{"on": false}} turns it off'


@dataclass(frozen=True, slots=True)
class StoredJudge:
    """A judge as the org keeps it: whose it is ('' the org's), who wrote it last, and when."""

    spec: JudgeSpec
    agent: str
    author: str
    set_at: datetime


async def judges_at(session: AsyncSession, org: str, agent: str) -> list[StoredJudge]:
    """The judges written at one level, the org's (agent '') or an agent's own, by name."""
    return [_stored(row) for row in await JudgeRepository(session).at_level(org, agent)]


async def own_judges_for(session: AsyncSession, org: str, agent: str) -> list[JudgeSpec]:
    """Every judge of the org's a call of the agent is held to: the org's, then its own."""
    return [_spec_of_row(row) for row in await JudgeRepository(session).for_call(org, agent)]


async def judge_named(session: AsyncSession, org: str, agent: str, name: str) -> JudgeSpec:
    """One of Pinecall's judges by its name, else the org's or the agent's own; else a 404."""
    found = catalog.library_judges().get(name)
    if found is not None:
        return found.spec
    own = {spec.name: spec for spec in await own_judges_for(session, org, agent)}
    if name not in own:
        raise NotFound(NOBODY.format(whose=agent, name=name))
    return own[name]


# One of Pinecall's is switched, one of the org's own is written whole; never the other way.
async def write_judge(session: AsyncSession, org: str, agent: str, name: str, body: JudgeRequest, *, by: str) -> None:
    """Switch one of Pinecall's judges for the level, or write one of the org's own there."""
    if name in catalog.library_judges():
        if body.on is None or body.model_fields_set - {"on"}:
            raise Conflict(ONLY_ON.format(name=name))
        await JudgeSwitchRepository(session).switch(org, agent, (name,), on=body.on, author=by)
        return
    if body.on is not None:
        raise Conflict(NOT_A_SWITCH.format(name=name))
    await put_judge(session, org, agent, spec_of(name, body), by=by)


async def put_judge(session: AsyncSession, org: str, agent: str, spec: JudgeSpec, *, by: str) -> None:
    """Write a judge whole, the org's (agent '') or one agent's; the same name again replaces it."""
    repository = JudgeRepository(session)
    clash = await repository.clashing(org, agent, spec.name)
    if clash is not None:
        raise Conflict(TAKEN.format(name=spec.name, whose=_owner(clash)))
    await repository.put(
        org,
        agent,
        name=spec.name,
        question=spec.question,
        answer=spec.answer,
        choices=spec.choices,
        runs_when=spec.on,
        trigger=spec.trigger,
        reads=spec.reads,
        author=by,
    )


async def delete_judge(session: AsyncSession, org: str, agent: str, name: str) -> None:
    """Forget one of the org's own judges; 404 for a name nobody wrote, 409 for Pinecall's."""
    if name in catalog.library_judges():
        raise Conflict(NOT_YOURS.format(name=name))
    if not await JudgeRepository(session).drop(org, agent, name):
        raise NotFound(NOBODY.format(whose=_owner(agent), name=name))


async def switches_for(session: AsyncSession, org: str, agent: str) -> dict[str, bool]:
    """Which of the library's judges the agent's calls run, as the org and the agent set them."""
    return await JudgeSwitchRepository(session).for_agent(org, agent)


async def switched_at(session: AsyncSession, org: str, agent: str) -> dict[str, bool]:
    """The switches written at one level alone: the org's (agent '') or an agent's own."""
    return await JudgeSwitchRepository(session).at_level(org, agent)


async def switch_judges(
    session: AsyncSession, org: str, agent: str, names: Sequence[str], *, on: bool, by: str
) -> None:
    """Turn library judges on or off, for the org (agent '') or for one agent."""
    await JudgeSwitchRepository(session).switch(org, agent, names, on=on, author=by)


# An agent's list carries the org's own too, since its calls meet them; the org's ('') is the
# org's alone.
async def list_judges(session: AsyncSession, org: str, agent: str) -> list[JudgeRow]:
    """Every judge the agent's calls may meet: Pinecall's as switched, the org's own, the agent's."""
    switches = await switches_for(session, org, agent)
    rows = [_library_row(judge, switches) for judge in catalog.library_judges().values()]
    rows += [
        _own_row(stored) for stored in (_stored(row) for row in await JudgeRepository(session).for_call(org, agent))
    ]
    return rows


def spec_of(name: str, body: JudgeRequest) -> JudgeSpec:
    """A judge as a request writes it."""
    reads = set(body.reads)
    return JudgeSpec(
        name=name,
        question=body.question,
        answer=body.answer,
        choices=tuple(body.choices),
        on=body.when,
        trigger=body.trigger,
        reads_prompt="prompt" in reads,
        reads_evidence="evidence" in reads,
        reads_facts="facts" in reads,
    )


def _spec_of_row(row: AgentJudge) -> JudgeSpec:
    reads = {str(item) for item in row.reads}
    return JudgeSpec(
        name=row.name,
        question=row.question,
        answer=row.answer,
        choices=tuple(str(choice) for choice in row.choices),
        on=row.runs_when,
        trigger=row.trigger,
        reads_prompt="prompt" in reads,
        reads_evidence="evidence" in reads,
        reads_facts="facts" in reads,
    )


def _stored(row: AgentJudge) -> StoredJudge:
    return StoredJudge(spec=_spec_of_row(row), agent=row.agent, author=row.author, set_at=row.set_at)


def _library_row(judge: catalog.Written, switches: dict[str, bool]) -> JudgeRow:
    return _row(
        judge.spec,
        owner=PINECALL,
        on=switches.get(judge.spec.name, judge.on_by_default),
        summary=judge.summary,
        version=judge.version,
        why=judge.why,
        recommended=judge.recommended,
    )


def _own_row(stored: StoredJudge) -> JudgeRow:
    return _row(
        stored.spec, owner=stored.agent or THE_ORG, on=True, author=stored.author, set_at=stored.set_at.timestamp()
    )


def _row(
    spec: JudgeSpec,
    *,
    owner: str,
    on: bool,
    summary: str | None = None,
    version: int | None = None,
    why: str | None = None,
    recommended: bool = False,
    author: str | None = None,
    set_at: float | None = None,
) -> JudgeRow:
    return JudgeRow(
        name=spec.name,
        owner=owner,
        on=on,
        question=spec.question,
        answer=spec.answer,
        choices=list(spec.choices),
        when=spec.on,
        trigger=spec.trigger,
        reads=list(spec.reads),
        summary=summary,
        version=version,
        why=why,
        recommended=recommended,
        author=author,
        set_at=set_at,
    )


def _owner(agent: str) -> str:
    """The owner of a judge as a sentence names it: the org, or the agent's slug."""
    return "the org" if agent == THE_ORGS_OWN else agent
