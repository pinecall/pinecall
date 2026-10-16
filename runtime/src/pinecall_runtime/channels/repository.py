"""The routes table, with the carrier each number lives in, and the WhatsApp messages seen."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert

from pinecall_runtime.channels.models import Route, WhatsappSeen
from pinecall_runtime.enums import Channel, Env, RouteOrigin
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.kit.time import now
from pinecall_runtime.postgres import box_wide

# A number rung all day is written once a minute, never once a call.
CALLED_EVERY = timedelta(minutes=1)


class RouteRepository(Repository[Route]):
    """Which agent answers a number, per org and env."""

    model = Route

    async def of_org(self, org: str, env: Env) -> Sequence[Route]:
        """The org's numbers in one env, oldest first."""
        return await self.all(
            self.statement().where(Route.org == org, Route.env == env).order_by(Route.added_at, Route.number)
        )

    async def phones_of(self, org: str) -> Sequence[Route]:
        """The org's phone numbers in both envs, oldest first."""
        statement = (
            self.statement()
            .where(Route.org == org, Route.channel == Channel.phone)
            .order_by(Route.added_at, Route.number)
        )
        return await self.all(statement)

    async def get(self, org: str, number: str) -> Route | None:
        """The org's route at this number, whatever env it is in."""
        return await self.one_or_none(self.statement().where(Route.org == org, Route.number == number))

    # One org holds a number (routes_number_held_once), so a number reads one row at most.
    async def at(self, channel: Channel, number: str) -> Route | None:
        """The route a call dialled to this number takes, whatever org holds it."""
        with box_wide():
            return await self.one_or_none(self.statement().where(Route.channel == channel, Route.number == number))

    # A number added again moves: its agent, channel, env and how it came are the newest said. One
    # written to wait (a hooked number, where the box asks for approval) is unapproved until the
    # operator approves it; one approved once stays approved however it comes again.
    async def put(
        self,
        org: str,
        number: str,
        *,
        agent: str,
        channel: Channel,
        env: Env,
        managed: bool,
        account: str | None,
        networks: Sequence[str],
        origin: RouteOrigin,
        via: str | None,
        waits: bool,
    ) -> Route:
        """Keep the route, moving the number if the org had it, with how it was written."""
        row = await self.get(org, number)
        approved_at = None if waits else now()
        if row is None:
            return await self.add(
                Route(
                    org=org,
                    number=number,
                    agent=agent,
                    channel=channel,
                    env=env,
                    managed=managed,
                    account=account,
                    networks=list(networks),
                    origin=origin,
                    via=via,
                    approved_at=approved_at,
                )
            )
        return await self.update(
            row,
            agent=agent,
            channel=channel,
            env=env,
            managed=managed,
            account=account,
            networks=list(networks),
            origin=origin,
            via=via,
            approved_at=row.approved_at or approved_at,
        )

    async def called(self, org: str, number: str) -> None:
        """Note that a call to the org's number reached the box now."""
        at = now()
        await self.session.execute(
            update(Route)
            .where(
                Route.org == org,
                Route.number == number,
                (Route.last_call_at.is_(None)) | (Route.last_call_at < at - CALLED_EVERY),
            )
            .values(last_call_at=at)
        )

    async def approve(self, org: str, number: str, by: str) -> bool:
        """The operator's word that the org's hooked number is the org's; whether one waited."""
        statement = (
            update(Route)
            .where(Route.org == org, Route.number == number, Route.approved_at.is_(None))
            .values(approved_at=now(), approved_by=by)
        )
        return bool(await self.changed(statement))

    async def held_elsewhere(self, org: str, number: str) -> bool:
        """Whether another org holds the number on this box."""
        with box_wide():
            statement = select(exists().where(Route.number == number, Route.org != org))
            return bool((await self.session.execute(statement)).scalar_one())

    async def remove(self, org: str, number: str) -> bool:
        """Forget the org's route at the number; whether there was one."""
        return bool(await self.changed(delete(Route).where(Route.org == org, Route.number == number)))

    async def move(self, org: str, number: str, env: Env) -> bool:
        """Move the org's number into the env; whether it had it."""
        return bool(await self.changed(update(Route).where(Route.org == org, Route.number == number).values(env=env)))

    # A number the target org already typed stays where it was: one row per number per org.
    async def move_with_agent(self, agent: str, org: str) -> tuple[list[str], list[str]]:
        """Move the agent's numbers into the org; the numbers moved, and the ones that stayed."""
        with box_wide():
            theirs = select(Route.number).where(Route.org == org)
            moved = await self.session.execute(
                update(Route)
                .where(Route.agent == agent, Route.org != org, Route.number.not_in(theirs))
                .values(org=org)
                .returning(Route.number)
            )
            stayed = await self.session.execute(
                select(Route.number).where(Route.agent == agent, Route.org != org).order_by(Route.number)
            )
        return sorted(str(number) for number in moved.scalars()), [str(number) for number in stayed.scalars()]

    async def managed_in(self, org: str, env: Env) -> int:
        """How many of the org's numbers in the env the box bought."""
        statement = (
            select(func.count()).select_from(Route).where(Route.org == org, Route.env == env, Route.managed.is_(True))
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def orgs_with_phones(self) -> list[str]:
        """Every org that answers at a phone number, by id."""
        with box_wide():
            statement = select(Route.org).where(Route.channel == Channel.phone).distinct().order_by(Route.org)
            return [str(org) for org in (await self.session.execute(statement)).scalars()]


type CarrierKindRow = str | None


class WhatsappSeenRepository(Repository[WhatsappSeen]):
    """The message ids Meta delivered, claimed by one delivery and read once."""

    model = WhatsappSeen

    async def get(self, org: str, message_id: str) -> WhatsappSeen | None:
        """The row of the message, or None."""
        return await self.one_or_none(
            self.statement().where(WhatsappSeen.org == org, WhatsappSeen.message_id == message_id)
        )

    # The insert is the check, in one statement: of two deliveries at once, one inserts and the
    # other finds the row; a claim left unread past its lease is taken over in the same statement.
    async def claim(self, org: str, message_id: str, *, at: datetime, stale_before: datetime) -> bool:
        """Claim the message for this delivery; False when another read it or is reading it."""
        statement = insert(WhatsappSeen).values(org=org, message_id=message_id, claimed_at=at)
        claimed = statement.on_conflict_do_update(
            index_elements=[WhatsappSeen.org, WhatsappSeen.message_id],
            set_={"claimed_at": statement.excluded.claimed_at},
            where=(WhatsappSeen.read_at.is_(None)) & (WhatsappSeen.claimed_at < stale_before),
        ).returning(WhatsappSeen.org)
        return (await self.session.execute(claimed)).scalar_one_or_none() is not None

    async def mark_read(self, org: str, message_id: str, *, at: datetime) -> None:
        """The claimed message is read: every later delivery of it is dropped."""
        await self.session.execute(
            update(WhatsappSeen)
            .where(WhatsappSeen.org == org, WhatsappSeen.message_id == message_id)
            .values(read_at=at)
        )

    async def release(self, org: str, message_id: str) -> None:
        """Give up the claim of a message whose reading failed, so Meta's next delivery reads it."""
        await self.session.execute(
            delete(WhatsappSeen).where(WhatsappSeen.org == org, WhatsappSeen.message_id == message_id)
        )

    async def forget_before(self, before: datetime) -> int:
        """Forget the message ids claimed longer ago than Meta retries; how many."""
        return await self.changed(delete(WhatsappSeen).where(WhatsappSeen.claimed_at < before))
