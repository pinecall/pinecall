"""An app's owed events, its runs and each run's journal: the queries and the leases."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, select, update
from sqlalchemy.dialects.postgresql import insert

from runtime.actor import Scope
from runtime.calls.models import CallFact
from runtime.enums import PARKED, RunStatus
from runtime.flows.models import AppEvent, FlowRun, FlowStep
from runtime.kit.repository import Repository
from runtime.kit.text import JsonObject


# The two travel together through every query and every use case: until 2026-11 each took both.
@dataclass(frozen=True, slots=True)
class App:
    """An app as its events and runs are kept: the scope its key acts in, and its name."""

    scope: Scope
    name: str


@dataclass(frozen=True, slots=True)
class CalledRun:
    """A run that waits for its call no longer: whether the call ended, and how."""

    run: FlowRun
    ended: bool
    end_reason: str | None


class EventRepository(Repository[AppEvent]):
    """The events an app is owed, oldest first."""

    model = AppEvent

    async def lease_owed(self, app: App, now: datetime, until: datetime, most: int) -> Sequence[AppEvent]:
        """Take the app's unheard events nobody holds, and hold them until `until`."""
        scope = app.scope
        statement = (
            self.statement()
            .where(AppEvent.org == scope.org, AppEvent.env == scope.env, AppEvent.app == app.name)
            .where(AppEvent.heard_at.is_(None))
            .where((AppEvent.leased_until.is_(None)) | (AppEvent.leased_until < now))
            .order_by(AppEvent.id)
            .limit(most)
            .with_for_update(skip_locked=True)
        )
        owed = await self.all(statement)
        for event in owed:
            event.leased_until = until
        return owed

    async def mark_heard(self, app: App, event_id: int, now: datetime) -> bool:
        """The app heard it; whether it was the app's and still owed."""
        scope = app.scope
        statement = (
            update(AppEvent)
            .where(AppEvent.id == event_id, AppEvent.org == scope.org, AppEvent.env == scope.env)
            .where(AppEvent.app == app.name, AppEvent.heard_at.is_(None))
            .values(heard_at=now)
        )
        return await self.change(statement) > 0


class RunRepository(Repository[FlowRun]):
    """The runs of an app's flows."""

    model = FlowRun

    def _of(self, app: App) -> Select[FlowRun]:
        scope = app.scope
        return self.statement().where(FlowRun.org == scope.org, FlowRun.env == scope.env, FlowRun.app == app.name)

    async def find(self, app: App, run: str, *, locked: bool = False) -> FlowRun | None:
        """The app's run by its id, or None; `locked` holds its row until the transaction ends."""
        statement = self._of(app).where(FlowRun.id == run)
        return await self.one_or_none(statement.with_for_update() if locked else statement)

    # One statement decides who started the run: until 2026-11 the key was read and then the run added, and
    # of two starts of one key at once the loser met the unique index as a database error, not "the same run".
    async def create_once(self, app: App, run: str, flow: str, key: str, given: JsonObject, at: datetime) -> FlowRun:
        """Start the run under this id unless the key already started one; the run the key names, either way."""
        scope = app.scope
        made = insert(FlowRun).values(
            id=run,
            org=scope.org,
            env=scope.env,
            app=app.name,
            flow=flow,
            key=key,
            input=given,
            status=RunStatus.ready,
            started_at=at,
            moved_at=at,
        )
        await self.session.execute(made.on_conflict_do_nothing(index_elements=["org", "env", "app", "flow", "key"]))
        started = self._of(app).where(FlowRun.flow == flow, FlowRun.key == key)
        return await self.one(started.execution_options(populate_existing=True))

    async def lease_ready(self, app: App, now: datetime, until: datetime, most: int) -> Sequence[FlowRun]:
        """Take the app's ready runs nobody holds, and hold them until `until`."""
        statement = (
            self._of(app)
            .where(FlowRun.status == RunStatus.ready)
            .where((FlowRun.leased_until.is_(None)) | (FlowRun.leased_until < now))
            .order_by(FlowRun.moved_at)
            .limit(most)
            .with_for_update(skip_locked=True)
        )
        ready = await self.all(statement)
        for run in ready:
            run.leased_until = until
        return ready

    async def list_newest(self, app: App, flow: str | None, status: RunStatus | None, most: int) -> Sequence[FlowRun]:
        """The app's runs, newest first, of one flow or in one status when named."""
        statement = self._of(app)
        if flow is not None:
            statement = statement.where(FlowRun.flow == flow)
        if status is not None:
            statement = statement.where(FlowRun.status == status)
        return await self.all(statement.order_by(FlowRun.started_at.desc()).limit(most))

    async def list_waiting_on(self, app: App, name: str) -> Sequence[FlowRun]:
        """The app's runs waiting for an event of this name, their rows held."""
        statement = self._of(app).where(FlowRun.status == RunStatus.waiting, FlowRun.waits_for == name)
        return await self.all(statement.with_for_update(skip_locked=True))

    async def list_due(self, now: datetime, most: int) -> Sequence[FlowRun]:
        """Runs of any org whose sleep is over or whose wait gave up, their rows held."""
        statement = (
            self.statement()
            .where(FlowRun.status.in_((RunStatus.sleeping, RunStatus.waiting)), FlowRun.wake_at <= now)
            .order_by(FlowRun.wake_at)
            .limit(most)
            .with_for_update(skip_locked=True)
        )
        return await self.all(statement)

    # One statement, in order, of the runs there is something to do for. Until 2026-11 a pass took fifty
    # runs that were calling, in no order, and then asked for their calls' facts: fifty whose call never
    # showed an end filled every pass, and no other run that was calling, of any org, woke again. A run
    # reads the call's facts as its own table (flows stands above calls); only the run's row is held.
    async def list_called_and_over(self, now: datetime, most: int) -> list[CalledRun]:
        """Runs of any org whose call ended, or was waited for until its hour; the longest waiting first, rows held."""
        statement = (
            select(FlowRun, CallFact.ended_at, CallFact.end_reason)
            .outerjoin(CallFact, CallFact.call == FlowRun.call)
            .where(FlowRun.status == RunStatus.calling)
            .where(CallFact.ended_at.is_not(None) | (FlowRun.wake_at <= now))
            .order_by(FlowRun.moved_at)
            .limit(most)
            .with_for_update(skip_locked=True, of=FlowRun)
        )
        rows = (await self.session.execute(statement)).all()
        return [CalledRun(row[0], row[1] is not None, row[2]) for row in rows]

    async def count_parked(self, org: str) -> int:
        """How many of the org's runs wait for something."""
        return await self.count(self.statement().where(FlowRun.org == org, FlowRun.status.in_(PARKED)))


class StepRepository(Repository[FlowStep]):
    """A run's journal."""

    model = FlowStep

    async def list_of_run(self, run: str) -> Sequence[FlowStep]:
        """The run's steps in order."""
        return await self.all(self.statement().where(FlowStep.run == run).order_by(FlowStep.seq))

    async def list_of_runs(self, runs: Sequence[str]) -> Sequence[FlowStep]:
        """Every step of these runs, each run's in order."""
        if not runs:
            return []
        return await self.all(self.statement().where(FlowStep.run.in_(runs)).order_by(FlowStep.run, FlowStep.seq))

    async def count_of_run(self, run: str) -> int:
        """How many steps the run's journal holds."""
        return await self.count(self.statement().where(FlowStep.run == run))

    async def find_at(self, run: str, seq: int) -> FlowStep | None:
        """The run's step at this place, or None."""
        return await self.one_or_none(self.statement().where(FlowStep.run == run, FlowStep.seq == seq))

    async def find_open(self, run: str) -> FlowStep | None:
        """The run's step that is not over, or None."""
        statement = self.statement().where(FlowStep.run == run, FlowStep.result.is_(None)).order_by(FlowStep.seq)
        return await self.one_or_none(statement.limit(1))
