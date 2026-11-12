"""What the fleets say on `/metrics`: each one's workers, seats and rooms waiting, and how each worker stands."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.fleet.service import slots
from runtime.fleet.service.roster import Roster
from runtime.fleet.service.totals import Listing, list_fleets
from runtime.kit.prometheus import family
from runtime.postgres import DatabaseError


class FleetMetrics:
    """Both envs' fleets as the roster hears them: their totals, each worker's state and first audio."""

    def __init__(self, roster: Roster, sessions: async_sessionmaker[AsyncSession]) -> None:
        """What it reads."""
        self._roster = roster
        self._sessions = sessions

    async def collect(self, now: float) -> str:
        """Each fleet's totals, each worker's state, each worker's first audio heard lately."""
        listing = await self._list(now)
        if listing is None:
            return ""
        by_fleet = {total.fleet: [w for w in listing.workers if w.fleet == total.fleet] for total in listing.totals}
        return "".join(
            (
                family(
                    "pinecall_fleet",
                    "Each fleet: workers, seats, calls held, accepting; rooms waiting for a worker.",
                    "gauge",
                    [
                        ({"fleet": total.fleet, "what": what}, value)
                        for total in listing.totals
                        for what, value in (
                            ("workers", total.workers),
                            ("seats", total.slots),
                            ("busy", total.active),
                            ("accepting", total.accepting),
                            ("waiting", total.waiting),
                        )
                    ],
                ),
                family(
                    "pinecall_worker_state",
                    "How the roster counts each worker: accepting, failing, full, draining, cordoned.",
                    "gauge",
                    [
                        ({"fleet": named, "worker": worker.worker, "state": state}, 1)
                        for named, workers in by_fleet.items()
                        for worker in workers
                        if (state := slots.state_of(worker, workers, now)) != "gone"
                    ],
                ),
                family(
                    "pinecall_worker_first_audio_p95_seconds",
                    "Each worker's first audio at the p95 over its last minute, as its heartbeat says.",
                    "gauge",
                    [
                        ({"fleet": named, "worker": worker.worker}, worker.first_audio_p95_s)
                        for named, workers in by_fleet.items()
                        for worker in workers
                        if worker.first_audio_p95_s is not None and slots.is_heard(worker, now)
                    ],
                ),
            )
        )

    # A database that cannot say leaves the fleets out: the scrape still answers.
    async def _list(self, now: float) -> Listing | None:
        try:
            async with self._sessions() as session:
                return await list_fleets(session, self._roster, now)
        except DatabaseError:
            return None
