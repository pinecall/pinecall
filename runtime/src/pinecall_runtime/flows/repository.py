"""An app's owed events, its runs and each run's journal: the queries, the leases and the moves."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from pinecall_runtime.flows.models import AppEvent, FlowRun, FlowStep
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.repository import Repository

# What a run waits in: each is woken by the clock, an event or a call's end.
PARKED = ("sleeping", "waiting", "calling")
OVER = ("done", "failed", "cancelled")


class EventRepository(Repository[AppEvent]):
    """The events an app is owed, oldest first."""

    model = AppEvent

    async def lease_owed(self, scope: Scope, app: str, now: datetime, until: datetime, most: int) -> Sequence[AppEvent]:
        """Take the app's unheard events nobody holds, and hold them until `until`."""
        statement = (
            self.statement()
            .where(
                AppEvent.org == scope.org, AppEvent.env == scope.env, AppEvent.app == app, AppEvent.heard_at.is_(None)
            )
            .where((AppEvent.leased_until.is_(None)) | (AppEvent.leased_until < now))
            .order_by(AppEvent.id)
            .limit(most)
            .with_for_update(skip_locked=True)
        )
        owed = await self.all(statement)
        for event in owed:
            event.leased_until = until
        return owed

    async def mark_heard(self, scope: Scope, app: str, event_id: int, now: datetime) -> bool:
        """The app heard it; whether it was the app's and still owed."""
        statement = (
            update(AppEvent)
            .where(AppEvent.id == event_id, AppEvent.org == scope.org, AppEvent.env == scope.env, AppEvent.app == app)
            .where(AppEvent.heard_at.is_(None))
            .values(heard_at=now)
        )
        return await self.changed(statement) > 0


class RunRepository(Repository[FlowRun]):
    """The runs of an app's flows."""

    model = FlowRun

    def _of(self, scope: Scope, app: str) -> Any:
        return self.statement().where(FlowRun.org == scope.org, FlowRun.env == scope.env, FlowRun.app == app)

    async def by_id(self, scope: Scope, app: str, run: str, *, locked: bool = False) -> FlowRun | None:
        """The app's run by its id, or None; `locked` holds its row until the transaction ends."""
        statement = self._of(scope, app).where(FlowRun.id == run)
        return await self.one_or_none(statement.with_for_update() if locked else statement)

    async def by_key(self, scope: Scope, app: str, flow: str, key: str) -> FlowRun | None:
        """The run this key started, or None."""
        return await self.one_or_none(self._of(scope, app).where(FlowRun.flow == flow, FlowRun.key == key))

    async def lease_ready(self, scope: Scope, app: str, now: datetime, until: datetime, most: int) -> Sequence[FlowRun]:
        """Take the app's ready runs nobody holds, and hold them until `until`."""
        statement = (
            self._of(scope, app)
            .where(FlowRun.status == "ready")
            .where((FlowRun.leased_until.is_(None)) | (FlowRun.leased_until < now))
            .order_by(FlowRun.moved_at)
            .limit(most)
            .with_for_update(skip_locked=True)
        )
        ready = await self.all(statement)
        for run in ready:
            run.leased_until = until
        return ready

    async def listed(
        self, scope: Scope, app: str, flow: str | None, status: str | None, most: int
    ) -> Sequence[FlowRun]:
        """The app's runs, newest first, of one flow or in one status when named."""
        statement = self._of(scope, app)
        if flow is not None:
            statement = statement.where(FlowRun.flow == flow)
        if status is not None:
            statement = statement.where(FlowRun.status == status)
        return await self.all(statement.order_by(FlowRun.started_at.desc()).limit(most))

    async def waiting_on(self, scope: Scope, app: str, name: str) -> Sequence[FlowRun]:
        """The app's runs waiting for an event of this name, their rows held."""
        statement = self._of(scope, app).where(FlowRun.status == "waiting", FlowRun.waits_for == name)
        return await self.all(statement.with_for_update(skip_locked=True))

    async def due(self, now: datetime, most: int) -> Sequence[FlowRun]:
        """Runs of any org whose sleep is over or whose wait gave up, their rows held."""
        statement = (
            self.statement()
            .where(FlowRun.status.in_(("sleeping", "waiting")), FlowRun.wake_at <= now)
            .order_by(FlowRun.wake_at)
            .limit(most)
            .with_for_update(skip_locked=True)
        )
        return await self.all(statement)

    async def calling(self, most: int) -> Sequence[FlowRun]:
        """Runs of any org waiting for the call they placed to end, their rows held."""
        statement = self.statement().where(FlowRun.status == "calling").limit(most).with_for_update(skip_locked=True)
        return await self.all(statement)

    async def parked_count(self, org: str) -> int:
        """How many of the org's runs wait for something."""
        return await self.count(self.statement().where(FlowRun.org == org, FlowRun.status.in_(PARKED)))


class StepRepository(Repository[FlowStep]):
    """A run's journal."""

    model = FlowStep

    async def of_run(self, run: str) -> Sequence[FlowStep]:
        """The run's steps in order."""
        return await self.all(self.statement().where(FlowStep.run == run).order_by(FlowStep.seq))

    async def of_runs(self, runs: Sequence[str]) -> Sequence[FlowStep]:
        """Every step of these runs, each run's in order."""
        if not runs:
            return []
        return await self.all(select(FlowStep).where(FlowStep.run.in_(runs)).order_by(FlowStep.run, FlowStep.seq))

    async def at(self, run: str, seq: int) -> FlowStep | None:
        """The run's step at this place, or None."""
        return await self.one_or_none(self.statement().where(FlowStep.run == run, FlowStep.seq == seq))

    async def open_of(self, run: str) -> FlowStep | None:
        """The run's step that is not over, or None."""
        statement = self.statement().where(FlowStep.run == run, FlowStep.result.is_(None)).order_by(FlowStep.seq)
        return await self.one_or_none(statement.limit(1))
