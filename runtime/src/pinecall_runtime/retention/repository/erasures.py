"""An erasure's statements: what a call, a contact, an agent or an org leaves, deleted; and its trail."""

from collections.abc import Sequence

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as upsert

from pinecall_runtime.accounts.models import ApiKey, Member, Org, Token
from pinecall_runtime.agents.models import AgentCanary, AgentConfig, AgentWidget, HoldAudio, Lexicon
from pinecall_runtime.alerts.models import Monitor
from pinecall_runtime.calls.models import (
    CallFact,
    CallLog,
    CallLogHead,
    CallOpening,
    CallPrivate,
    DriftCall,
    JudgeDay,
    StageDay,
    ThreadRead,
)
from pinecall_runtime.channels.models import Route
from pinecall_runtime.compliance.models import RecordingKey
from pinecall_runtime.enums import Channel, Env, ErasureKind
from pinecall_runtime.evals.models import EvalRun
from pinecall_runtime.judging.models import (
    AgentJudge,
    AgentPersona,
    CaseGroup,
    EvalCase,
    JudgeLabel,
    JudgeSwitch,
    PersonaSwitch,
)
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.knowledge.models import ContactMemory
from pinecall_runtime.retention.models import CallRecord, Erasure

# The trigger on call_log lets a DELETE through in the transaction that set this, and no other
# (migrations/sql/0011_erasure.sql).
LET_DELETES_THROUGH = text("SET LOCAL pinecall.erasing = 'on'")
A_TRAIL_PAGE = 100


class ErasureRepository(Repository[Erasure]):
    """Every delete an erasure makes, and the trail row it writes last."""

    model = Erasure

    async def let_deletes_through(self) -> None:
        """Tell call_log's trigger this transaction is an erasure."""
        await self.session.execute(LET_DELETES_THROUGH)

    # ── what there is to erase ──

    async def calls_of_contact(self, org: str, env: Env, contact: str) -> list[tuple[str, bool]]:
        """Every call of the contact in the env: the call and whether it is sealed."""
        statement = (
            select(CallLogHead.call, CallLogHead.sealed)
            .join(CallFact, CallFact.call == CallLogHead.call)
            .where(CallLogHead.org == org, CallLogHead.env == env, CallFact.contact == contact)
        )
        return [(str(call), bool(sealed)) for call, sealed in (await self.session.execute(statement)).all()]

    async def logs_of_org(self, org: str) -> Sequence[CallLogHead]:
        """Every log of the org: its calls, and its agents' own logs, which carry no call."""
        return (await self.session.scalars(select(CallLogHead).where(CallLogHead.org == org))).all()

    async def logs_of_agent(self, org: str, agent: str) -> Sequence[CallLogHead]:
        """Every log of one agent of the org, both envs and every holder: its calls and its own log."""
        statement = select(CallLogHead).where(CallLogHead.org == org, CallLogHead.agent == agent)
        return (await self.session.scalars(statement)).all()

    # ── a log's rows ──

    # Before the heads go: call_log's trigger reads each summary's org off its head, to take its
    # usage out of the org's totals (migrations/sql/0023_usage_totals.sql).
    async def erase_entries(self, logs: Sequence[str]) -> int:
        """Delete the logs' entries; how many."""
        return await self.changed(delete(CallLog).where(CallLog.log.in_(logs)))

    # A phone call's numbers, times and end stay in call_records: they name numbers and times,
    # never what was said, and a carrier's traceback asks for them (0016_call_records.sql).
    async def record_phone_calls(self, calls: Sequence[str]) -> None:
        """Write each phone call's record off its facts, before the facts go."""
        recorded = (
            select(
                CallFact.call,
                CallLogHead.org,
                CallLogHead.env,
                CallFact.direction,
                CallFact.from_number,
                CallFact.to_number,
                CallLogHead.started_at,
                CallFact.ended_at,
                CallFact.end_reason,
            )
            .join(CallLogHead, CallLogHead.call == CallFact.call)
            .where(CallFact.call.in_(calls), CallFact.channel == Channel.phone)
        )
        columns = [
            "call",
            "org",
            "env",
            "direction",
            "from_number",
            "to_number",
            "started_at",
            "ended_at",
            "end_reason",
        ]
        statement = upsert(CallRecord).from_select(columns, recorded).on_conflict_do_nothing(index_elements=["call"])
        await self.session.execute(statement)

    # What a call left besides its entries: the private values sealed beside them, its recording's
    # key, its head, facts and tokens, the memories it taught, the verdicts its day's drift counted
    # (the day's sums keep its numbers, which name nobody), the case made of it, the labels people
    # gave its judges, and what it was when it opened.
    async def erase_logs(self, logs: Sequence[str], calls: Sequence[str]) -> int:
        """Delete every row of the logs and their calls; how many memories the calls had taught."""
        await self.changed(delete(CallPrivate).where(CallPrivate.log.in_(logs)))
        await self.changed(delete(RecordingKey).where(RecordingKey.call.in_(calls)))
        await self.changed(delete(CallLogHead).where(CallLogHead.log.in_(logs)))
        await self.changed(delete(CallFact).where(CallFact.call.in_(calls)))
        await self.changed(delete(Token).where(Token.call.in_(calls)))
        taught = await self.changed(delete(ContactMemory).where(ContactMemory.source_call.in_(calls)))
        await self.changed(delete(DriftCall).where(DriftCall.call.in_(calls)))
        await self.changed(delete(EvalCase).where(EvalCase.source_call.in_(calls)))
        await self.changed(delete(JudgeLabel).where(JudgeLabel.call.in_(calls)))
        await self.changed(delete(CallOpening).where(CallOpening.call.in_(calls)))
        return taught

    # ── what else a subject owns ──

    async def erase_contact(self, org: str, env: Env, contact: str) -> int:
        """Delete the contact's memories no erased call taught, and what readers read of their thread."""
        memories = await self.changed(
            delete(ContactMemory).where(
                ContactMemory.org == org, ContactMemory.env == env, ContactMemory.contact == contact
            )
        )
        await self.changed(
            delete(ThreadRead).where(ThreadRead.org == org, ThreadRead.env == env, ThreadRead.contact == contact)
        )
        return memories

    # What has no foreign key to the org: its eval runs (by the org they carry, or by its agents for
    # a run written before runs carried one), hold melodies, thread reads and keys, revoked ones
    # included. Then the org, and the quotas, carriers, settings and memories cascade.
    async def erase_org(self, org: str, agents: Sequence[str]) -> None:
        """Delete the org and everything that hangs off it."""
        orphaned = (EvalRun.org.is_(None)) & EvalRun.agent.in_(agents)
        await self.changed(delete(EvalRun).where(or_(EvalRun.org == org, orphaned)))
        await self.changed(delete(HoldAudio).where(HoldAudio.org == org))
        await self.changed(delete(ThreadRead).where(ThreadRead.org == org))
        await self.changed(delete(ApiKey).where(ApiKey.org == org))
        await self.changed(delete(Org).where(Org.id == org))

    # What the org keeps of one agent besides its logs, in both envs: its settings and their
    # versions, canary, widget, hold melody and lexicon, personas, judges and monitors, the numbers
    # that route to it, its eval runs and cases, its days of drift, thread reads and tokens. A
    # person held to a list of agents loses this one from it. The dials ledger stays.
    async def erase_agent(self, org: str, agent: str) -> None:
        """Delete every row the org keeps of the agent."""
        owned = (
            (AgentConfig, AgentConfig.agent),
            (AgentCanary, AgentCanary.agent),
            (AgentWidget, AgentWidget.agent),
            (HoldAudio, HoldAudio.agent),
            (Lexicon, Lexicon.agent),
            (AgentPersona, AgentPersona.agent),
            (AgentJudge, AgentJudge.agent),
            (JudgeSwitch, JudgeSwitch.agent),
            (PersonaSwitch, PersonaSwitch.agent),
            (Monitor, Monitor.agent),
            (Route, Route.agent),
            (EvalRun, EvalRun.agent),
            (EvalCase, EvalCase.agent),
            (CaseGroup, CaseGroup.agent),
            (DriftCall, DriftCall.agent),
            (JudgeDay, JudgeDay.agent),
            (StageDay, StageDay.agent),
            (JudgeLabel, JudgeLabel.agent),
            (ThreadRead, ThreadRead.agent),
            (Token, Token.agent),
        )
        for model, column in owned:
            await self.changed(delete(model).where(model.org == org, column == agent))
        statement = (
            update(Member)
            .where(Member.org == org, Member.agents.contains([agent]))
            .values(agents=func.array_remove(Member.agents, agent))
        )
        await self.changed(statement)

    # ── the trail ──

    async def add_trail(
        self,
        *,
        org: str,
        env: Env | None,
        what: ErasureKind,
        subject: str,
        asked_by: str,
        calls: int,
        entries: int,
        memories: int,
        recordings: int,
    ) -> Erasure:
        """Write the erasure down; the row with its id and time."""
        row = Erasure(
            org=org,
            env=env,
            what=what,
            subject=subject,
            asked_by=asked_by,
            calls=calls,
            entries=entries,
            memories=memories,
            recordings=recordings,
        )
        return await self.add(row)

    async def trail_of(self, org: str, *, limit: int = A_TRAIL_PAGE) -> Sequence[Erasure]:
        """The org's erasures, newest first."""
        statement = (
            self.statement().where(Erasure.org == org).order_by(Erasure.at.desc(), Erasure.id.desc()).limit(limit)
        )
        return await self.all(statement)
