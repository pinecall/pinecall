"""The offers table: every room with a caller and no worker yet, as the gateways share it."""

from collections.abc import Sequence

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from runtime.fleet.models import Offer
from runtime.kit.repository import Repository


class OfferRepository(Repository[Offer]):
    """The rooms waiting for a worker; every write is one statement, so two gateways never race."""

    model = Offer

    # The first sight stands: a second webhook for the same room changes nothing. A room whose call a
    # worker opened is kept anew, since it is offered again only because that worker left it.
    async def open(self, room: str, fleet: str, dispatch: str, now: float) -> Offer | None:
        """Keep a room a caller joined; the row as kept, or None when it waits for a worker already."""
        kept = insert(Offer).values(room=room, fleet=fleet, dispatch=dispatch, seen_at=now)
        statement = kept.on_conflict_do_update(
            index_elements=[Offer.room],
            set_={
                "fleet": fleet,
                "dispatch": dispatch,
                "seen_at": now,
                "worker": None,
                "offers": 0,
                "offered_at": None,
                "opened_at": None,
            },
            where=Offer.opened_at.is_not(None),
        ).returning(Offer)
        return (await self.session.execute(statement.execution_options(populate_existing=True))).scalar_one_or_none()

    # Taken only by the gateway that read this count: two sweeping the same room offer it once.
    async def claim(self, room: str, offers: int, worker: str, now: float) -> bool:
        """Say the room is offered to this worker; False when another gateway offered it first."""
        statement = (
            update(Offer)
            .where(Offer.room == room, Offer.offers == offers)
            .values(worker=worker, offers=Offer.offers + 1, offered_at=now)
            .returning(Offer.room)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

    async def list_due(self, before: float, limit: int) -> Sequence[Offer]:
        """The rooms no worker opened and nobody offered since `before`, oldest first."""
        statement = (
            self.statement()
            .where(Offer.opened_at.is_(None), (Offer.offered_at.is_(None)) | (Offer.offered_at < before))
            .order_by(Offer.seen_at)
            .limit(limit)
        )
        return await self.all(statement)

    async def count_due(self, fleet: str, before: float) -> int:
        """How many of the fleet's rooms no worker opened and nobody offered since `before`."""
        due = self.statement().where(
            Offer.fleet == fleet, Offer.opened_at.is_(None), (Offer.offered_at.is_(None)) | (Offer.offered_at < before)
        )
        return await self.count(due)

    async def list_in_flight(self, since: float) -> list[tuple[str, float | None]]:
        """Each room offered to a worker since `since` or opened by it since: the worker, and when it opened."""
        statement = select(Offer.worker, Offer.opened_at).where(
            Offer.worker.is_not(None),
            or_(and_(Offer.opened_at.is_(None), Offer.offered_at >= since), Offer.opened_at >= since),
        )
        rows = (await self.session.execute(statement)).all()
        return [(str(worker), opened_at) for worker, opened_at in rows]

    async def count_waiting(self, since: float) -> dict[str, int]:
        """Each fleet's rooms with a caller seen since `since` that no worker opened."""
        statement = (
            select(Offer.fleet, func.count())
            .where(Offer.seen_at >= since, Offer.opened_at.is_(None))
            .group_by(Offer.fleet)
        )
        rows = (await self.session.execute(statement)).all()
        return {str(fleet): int(waiting) for fleet, waiting in rows}

    async def forget(self, room: str) -> None:
        """The room is done with: the overflow sent, or the room gone."""
        await self.session.execute(delete(Offer).where(Offer.room == room))

    async def mark_opened(self, room: str, now: float) -> None:
        """A worker has the room's call: nothing is left to offer, and the first word of it stands."""
        statement = update(Offer).where(Offer.room == room, Offer.opened_at.is_(None)).values(opened_at=now)
        await self.session.execute(statement)

    # Only while the room is still that worker's: one offered to another since is the other's to say.
    async def mark_dropped(self, room: str, worker: str) -> None:
        """The worker the room was offered to could not start its job: nobody has the room, and it is offered again."""
        statement = update(Offer).where(Offer.room == room, Offer.worker == worker).values(opened_at=None)
        await self.session.execute(statement)

    # Held to the end of the transaction, by every gateway alike: Postgres' advisory lock, keyed by the fleet.
    async def take_turns(self, fleet: str) -> None:
        """Wait for whoever is seating a call in the fleet now: its seats are asked for and taken one at a time."""
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"offers:{fleet}"))))

    async def forget_older_than(self, moment: float) -> None:
        """Rooms first seen before the moment are past any offer: their callers are gone."""
        await self.session.execute(delete(Offer).where(Offer.seen_at < moment))

    # Until 2026-11 this was `count_kept_since(before)`, which counted the rows before it.
    async def count_older_than(self, moment: float) -> int:
        """How many rooms were first seen before the moment and are still kept."""
        return await self.count(self.statement().where(Offer.seen_at < moment, Offer.opened_at.is_(None)))
