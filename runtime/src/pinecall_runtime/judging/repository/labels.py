"""The judge judged: calls a person labelled, and each judge's agreement with those labels."""

from dataclasses import dataclass

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as upsert

from pinecall_runtime.enums import Env
from pinecall_runtime.judging.models import JudgeLabel
from pinecall_runtime.kit.repository import Repository

# Each label beside the verdict the seal counted for the same judge on the same call, when one.
AGREEMENT = text("""
select label.judge,
       count(*) as labelled,
       count(verdict.held) as compared,
       count(*) filter (where verdict.held = label.held) as agreed
from judge_labels label
left join drift_calls counted on counted.call = label.call
left join lateral (
    select (item ->> 'held')::boolean as held
    from jsonb_array_elements(counted.verdicts) as item
    where item ->> 'judge' = label.judge
    limit 1
) verdict on true
where label.org = :org and label.env = :env
  and (cast(:agent as text) is null or label.agent = :agent)
group by label.judge
order by label.judge
""")


@dataclass(frozen=True, slots=True)
class AgreementRow:
    """One judge against the labels: how many, how many had its verdict beside them, agreed."""

    judge: str
    labelled: int
    compared: int
    agreed: int


class LabelRepository(Repository[JudgeLabel]):
    """One label per call and judge: what a person said the judge should have answered."""

    model = JudgeLabel

    async def put(
        self, *, call: str, judge: str, org: str, env: Env, agent: str, held: bool, note: str | None, author: str
    ) -> None:
        """Keep the label, replacing the one before it for the same call and judge."""
        statement = upsert(JudgeLabel).values(
            call=call, judge=judge, org=org, env=env, agent=agent, held=held, note=note, author=author
        )
        replaced = {
            "held": statement.excluded.held,
            "note": statement.excluded.note,
            "author": statement.excluded.author,
            "labelled_at": func.now(),
        }
        await self.session.execute(statement.on_conflict_do_update(index_elements=["call", "judge"], set_=replaced))

    async def agreement(self, org: str, env: Env, agent: str | None) -> list[AgreementRow]:
        """Each judge against the labels on the org's calls in the env, one agent's or all."""
        rows = (await self.session.execute(AGREEMENT, {"org": org, "env": env.value, "agent": agent})).all()
        return [
            AgreementRow(str(judge), int(labelled), int(compared), int(agreed))
            for judge, labelled, compared, agreed in rows
        ]
