"""A contact's threads with an agent: the inbox a person reads, what is unread, who was reached."""

from dataclasses import dataclass

from sqlalchemy import exists, func, select, text
from sqlalchemy.dialects.postgresql import insert

from pinecall_runtime.calls.models import CallFact, CallLogHead, ThreadRead
from pinecall_runtime.calls.repository.facts import facts_of_row
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.repository import Repository

# Unread for the reader: one per spoken call started since they read, one per line the contact
# wrote since then in a written call.
THREADS = text("""
with mine as (
    select f.*, head.agent, coalesce(head.started_at, -1) as at,
           coalesce(f.last_at, head.started_at, -1) as moved_at
    from call_log_head head join call_facts f on f.call = head.log
    where head.org = :org and head.env = :env and head.holder = :holder
      and head.agent = :agent and head.call is not null and f.contact is not null
), newest as (
    select distinct on (contact) *
    from mine order by contact, moved_at desc, call desc
), counted as (
    select mine.contact, count(*) as calls, max(mine.name) as any_name,
           sum(case when mine.spoken then (mine.at > coalesce(seen.read_at, 0))::int
                    else (select count(*) from unnest(mine.heard_at) as heard
                          where heard > coalesce(seen.read_at, 0))::int end) as unread
    from mine
    left join thread_reads seen
      on seen.org = :org and seen.env = :env and seen.holder = :holder
     and seen.agent = :agent and seen.reader = :reader and seen.contact = mine.contact
    group by mine.contact
)
select newest.*, counted.calls, counted.unread, coalesce(newest.name, counted.any_name) as known_as
from newest join counted on counted.contact = newest.contact
where cast(:moved_at as double precision) is null
   or (newest.moved_at, newest.contact) < (:moved_at, cast(:contact as text))
order by newest.moved_at desc, newest.contact desc
limit :limit
""")


@dataclass(frozen=True, slots=True)
class InboxRow:
    """One contact in an inbox: its newest call, when it moved, what the reader has not read."""

    contact: str
    newest: CallFact
    agent: str
    moved_at: float
    unread: int
    calls: int
    name: str | None


@dataclass(frozen=True, slots=True)
class InboxPage:
    """One page of an inbox and the cursor of the next."""

    rows: list[InboxRow]
    next: str | None


@dataclass(frozen=True, slots=True)
class Inbox:
    """Whose inbox: a scope, an agent and the person reading it."""

    scope: Scope
    agent: str
    reader: str


class InboxRepository(Repository[ThreadRead]):
    """The threads of an agent's contacts, and each reader's cursor on them."""

    model = ThreadRead

    async def threads(self, inbox: Inbox, *, after: str | None, limit: int) -> InboxPage:
        """One page of the inbox, the contact that moved last first, with the unread counts."""
        moved_at, contact = _after_the_cursor(after)
        params = {
            "org": inbox.scope.org,
            "env": inbox.scope.env.value,
            "holder": inbox.scope.holder,
            "agent": inbox.agent,
            "reader": inbox.reader,
            "moved_at": moved_at,
            "contact": contact,
            "limit": limit + 1,
        }
        rows = (await self.session.execute(THREADS, params)).all()
        found = [
            InboxRow(
                contact=str(row.contact),
                newest=facts_of_row(row),
                agent=str(row.agent),
                moved_at=float(row.moved_at),
                unread=int(row.unread or 0),
                calls=int(row.calls),
                name=row.known_as,
            )
            for row in rows
        ]
        last = found[limit - 1] if len(found) > limit else None
        return InboxPage(rows=found[:limit], next=None if last is None else f"{last.moved_at!r}:{last.contact}")

    async def calls_with(self, scope: Scope, agent: str, contact: str, *, limit: int) -> list[str]:
        """The contact's newest calls with the agent in the scope."""
        statement = (
            select(CallLogHead.log)
            .join(CallFact, CallFact.call == CallLogHead.log)
            .where(
                CallLogHead.org == scope.org,
                CallLogHead.env == scope.env,
                CallLogHead.holder == scope.holder,
                CallLogHead.agent == agent,
                CallLogHead.call.is_not(None),
                CallFact.contact == contact,
            )
            .order_by(CallLogHead.started_at.desc().nulls_last(), CallLogHead.log.desc())
            .limit(limit)
        )
        return [str(log) for log in (await self.session.execute(statement)).scalars()]

    # Any agent of the org, on purpose: a past contact allows a call back. In one env: a test call
    # from a phone in the sandbox never makes it dialable from production. Matched as stored.
    async def ever_reached(self, org: str, env: Env, contact: str) -> bool:
        """Whether the contact ever had a call with any agent of the org in the env."""
        reached = exists().where(
            CallLogHead.log == CallFact.call,
            CallLogHead.org == org,
            CallLogHead.env == env,
            CallLogHead.call.is_not(None),
            CallFact.contact == contact,
        )
        return bool((await self.session.execute(select(reached))).scalar_one())

    # A read cursor never moves back.
    async def mark_read(self, inbox: Inbox, contact: str, at: float) -> None:
        """Mark the contact's thread read up to that time for this reader."""
        statement = insert(ThreadRead).values(
            org=inbox.scope.org,
            env=inbox.scope.env,
            holder=inbox.scope.holder,
            agent=inbox.agent,
            reader=inbox.reader,
            contact=contact,
            read_at=at,
        )

        statement = statement.on_conflict_do_update(
            index_elements=[
                ThreadRead.org,
                ThreadRead.env,
                ThreadRead.holder,
                ThreadRead.agent,
                ThreadRead.reader,
                ThreadRead.contact,
            ],
            set_={"read_at": func.greatest(ThreadRead.read_at, statement.excluded.read_at)},
        )
        await self.session.execute(statement)


def _after_the_cursor(cursor: str | None) -> tuple[float | None, str | None]:
    if cursor is None or ":" not in cursor:
        return None, None
    moved_at, contact = cursor.split(":", 1)
    try:
        return float(moved_at), contact
    except ValueError:
        return None, None
