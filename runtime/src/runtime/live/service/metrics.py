"""What the live side says of itself on `/metrics`: the appends, the errors, the vendors failing, what it holds."""

from runtime.kit.prometheus import family, histogram
from runtime.live.parts import LiveParts
from runtime.live.service.entries import Appends
from runtime.providers import service as providers


class LiveMetrics:
    """The live side's measures: what it counted of the appends and the calls' errors, and what it holds now."""

    def __init__(self, live: LiveParts, appends: Appends) -> None:
        """What it reads."""
        self._live = live
        self._appends = appends

    async def collect(self, now: float) -> str:
        """The appends, the errors, what is held, the vendors failing, the orgs that spend strangely."""
        live, appends = self._live, self._appends
        failing = live.health.failing(now)
        vendors = sorted(set(providers.list_vendors()) | failing)
        errors = sorted(live.health.errors.items())
        return "".join(
            (
                histogram(
                    "pinecall_append_seconds",
                    "Time a worker's entry or batch took to be written, measured at the endpoint.",
                    appends.seconds,
                ),
                family(
                    "pinecall_entries_appended_total",
                    "Entries workers wrote through the append endpoints.",
                    "counter",
                    [({}, appends.entries)],
                ),
                family(
                    "pinecall_errors_total",
                    "Error entries workers wrote, by code and the vendor whose plugin failed.",
                    "counter",
                    [({"code": code, "vendor": vendor}, count) for (code, vendor), count in errors],
                ),
                family(
                    "pinecall_held",
                    "What the gateway holds now: live log readers, app sockets, calls served.",
                    "gauge",
                    [
                        ({"what": "log_readers"}, live.logs.readers),
                        ({"what": "app_sockets"}, live.sockets.count_here()),
                        ({"what": "calls_live"}, len(live.calls.list_served())),
                    ],
                ),
                family(
                    "pinecall_writer_waiting",
                    "Appends queued for the log's writer and not yet in a transaction.",
                    "gauge",
                    [({}, live.store.writer.waiting)],
                ),
                family(
                    "pinecall_vendor_failing",
                    "1 for a vendor over its error line in the last two minutes, as this gateway saw; "
                    "0 for every other vendor installed.",
                    "gauge",
                    [({"vendor": vendor}, int(vendor in failing)) for vendor in vendors],
                ),
                family(
                    "pinecall_spend_unusual",
                    "How many times its usual day an org's calls cost today, while they do.",
                    "gauge",
                    [({"org": org}, multiple) for org, multiple in sorted(live.spending.by_org.items())],
                ),
            )
        )
