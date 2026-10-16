"""Counters and histograms in memory, and the Prometheus text they are read as."""

from bisect import bisect_left
from collections.abc import Iterable, Mapping
from typing import Literal

type Rows = Iterable[tuple[Mapping[str, str], float]]
type Kind = Literal["gauge", "counter"]


class Histogram:
    """Observations counted into fixed buckets, with their sum."""

    def __init__(self, bounds: tuple[float, ...]) -> None:
        self.bounds = bounds
        self.counts = [0] * (len(bounds) + 1)
        self.total = 0.0

    def observe(self, value: float) -> None:
        """Count one observation in the first bucket whose bound holds it."""
        self.counts[bisect_left(self.bounds, value)] += 1
        self.total += value


def family(name: str, help_: str, kind: Kind, rows: Rows) -> str:
    """One gauge or counter family, a line per label set."""
    lines = [f"# HELP {name} {help_}", f"# TYPE {name} {kind}"]
    lines += [f"{name}{_labels(labels)} {_number(value)}" for labels, value in rows]
    return "\n".join(lines) + "\n"


def histogram(name: str, help_: str, observed: Histogram) -> str:
    """One histogram: cumulative buckets, the sum and the count."""
    lines = [f"# HELP {name} {help_}", f"# TYPE {name} histogram"]
    running = 0
    for bound, count in zip((*observed.bounds, float("inf")), observed.counts, strict=True):
        running += count
        lines.append(f'{name}_bucket{{le="{_number(bound)}"}} {running}')
    lines += [f"{name}_sum {_number(observed.total)}", f"{name}_count {running}"]
    return "\n".join(lines) + "\n"


def _labels(labels: Mapping[str, str]) -> str:
    if not labels:
        return ""
    escaped = (
        f'{key}="{value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")}"'
        for key, value in labels.items()
    )
    return "{" + ",".join(escaped) + "}"


def _number(value: float) -> str:
    return "+Inf" if value == float("inf") else repr(float(value))
