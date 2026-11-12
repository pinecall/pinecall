"""Which vendors are failing now: each vendor's calls of the last two minutes, counted in memory by a gateway."""

from collections import Counter, deque
from collections.abc import Iterable

# A stage's fallbacks are ordered by the last two minutes of each vendor: judged once five calls
# were handed it as a stage's first, and over the line once half of those calls saw it fail.
VENDOR_WINDOW_S = 120.0
CALLS_TO_JUDGE = 5
FAILED_SHARE = 0.5
# A busy window is thousands of calls: past this many, a vendor's oldest are forgotten early.
MOST_KEPT = 10_000


# Counted on the append path: a dictionary and a deque, no lock (one event loop). Not durable on
# purpose: a gateway that restarts judges every vendor anew, from the next five calls.
class VendorHealth:
    """What a gateway counted of the vendors since it started: the errors workers wrote, the calls each was handed."""

    def __init__(self) -> None:
        """Nothing counted yet."""
        # By the entry's code and the vendor whose plugin failed, "" when none did.
        self.errors: Counter[tuple[str, str]] = Counter()
        # By vendor: when a call was handed it first for a stage, and when a call saw it fail.
        self.handed: dict[str, deque[float]] = {}
        self.failures: dict[str, deque[tuple[float, str]]] = {}

    def count_error(self, code: str, vendor: str) -> None:
        """One error entry a worker wrote."""
        self.errors[(code, vendor)] += 1

    def count_failure(self, vendor: str, call: str, at: float) -> None:
        """A call saw the vendor fail: an error naming it, or its stage's switch away from it."""
        self.failures.setdefault(vendor, deque(maxlen=MOST_KEPT)).append((at, call))

    def count_handed(self, vendors: Iterable[str], at: float) -> None:
        """A call's stages were resolved with these vendors first, each counted once."""
        for vendor in set(vendors):
            self.handed.setdefault(vendor, deque(maxlen=MOST_KEPT)).append(at)

    def failing(self, at: float) -> frozenset[str]:
        """The vendors over their error line in the window up to now."""
        since = at - VENDOR_WINDOW_S
        for failures in self.failures.values():
            while failures and failures[0][0] < since:
                failures.popleft()
        over: set[str] = set()
        for vendor, handed in self.handed.items():
            while handed and handed[0] < since:
                handed.popleft()
            calls = len({call for _, call in self.failures.get(vendor, ())})
            if len(handed) >= CALLS_TO_JUDGE and calls >= FAILED_SHARE * len(handed):
                over.add(vendor)
        return frozenset(over)
