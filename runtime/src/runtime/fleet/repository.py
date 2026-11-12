"""The offers table: every room with a caller and no worker yet, as the gateways share it."""

from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from runtime.fleet.models import Offer
from runtime.kit.repository import Repository


class OfferRepository(Repository[Offer]):
    """The rooms waiting for a worker; every write is one statement, so two gateways never race."""

    model = Offer

    # The first sight stands: a second webhook for the same room changes nothing.
    async def open(self, room: str, fleet: str, dispatch: str, now: float) -> Offer | None:
        """Keep a room a caller joined; the row as kept, or None when it was kept already."""
        statement = (
            insert(Offer)
            .values(room=room, fleet=fleet, dispatch=dispatch, seen_at=now)
            .on_conflict_do_nothing(index_elements=[Offer.room])
            .returning(Offer)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

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
            .where((Offer.offered_at.is_(None)) | (Offer.offered_at < before))
            .order_by(Offer.seen_at)
            .limit(limit)
        )
        return await self.all(statement)

    async def count_in_flight(self, since: float) -> dict[str, int]:
        """Each worker's rooms offered since `since` that it has not opened."""
        statement = (
            select(Offer.worker, func.count())
            .where(Offer.worker.is_not(None), Offer.offered_at >= since)
            .group_by(Offer.worker)
        )
        rows = (await self.session.execute(statement)).all()
        return {str(worker): int(offered) for worker, offered in rows}

    async def count_waiting(self, since: float) -> dict[str, int]:
        """Each fleet's rooms with a caller seen since `since` that no worker opened."""
        statement = select(Offer.fleet, func.count()).where(Offer.seen_at >= since).group_by(Offer.fleet)
        rows = (await self.session.execute(statement)).all()
        return {str(fleet): int(waiting) for fleet, waiting in rows}

    async def forget(self, room: str) -> None:
        """The room is done with: its call opened, the overflow sent, or the room gone."""
        await self.session.execute(delete(Offer).where(Offer.room == room))

    async def forget_older_than(self, moment: float) -> None:
        """Rooms first seen before the moment are past any offer: their callers are gone."""
        await self.session.execute(delete(Offer).where(Offer.seen_at < moment))

    # Until 2026-11 this was `count_kept_since(before)`, which counted the rows before it.
    async def count_older_than(self, moment: float) -> int:
        """How many rooms were first seen before the moment and are still kept."""
        return await self.count(self.statement().where(Offer.seen_at < moment))
