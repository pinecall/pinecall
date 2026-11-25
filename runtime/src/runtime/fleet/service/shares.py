"""Whose turn a freed seat is: the org that holds the fewest, then the caller that waited longest."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Waiting:
    """A caller in the line for a seat: its room, whose it is, and when it first asked."""

    room: str
    org: str
    asked_at: float


# Seats went to whoever asked first: one org's comparison of sixty calls held every seat a caller that
# waits may take for twenty minutes, and another org's one call waited behind all of them (2026-11-25).
# A seat that frees now goes to the org that holds the fewest, so two orgs asking at once come to half
# each and three to a third, and an org that arrives while another holds everything is given the next
# seats that free. Nothing is held back for an org that is not asking, and nobody's call is ended to
# make room: the share is only ever in who is seated next. Among orgs that hold the same, and among
# one org's own callers, the longest wait goes first.
def list_next(waiting: Iterable[Waiting], held: Mapping[str, int], seats: int) -> list[str]:
    """The rooms the next `seats` seats go to, in the order they are given."""
    lines: dict[str, list[Waiting]] = {}
    for caller in sorted(waiting, key=lambda one: (one.asked_at, one.room)):
        lines.setdefault(caller.org, []).append(caller)
    holds = {org: held.get(org, 0) for org in lines}
    given: list[str] = []
    while lines and len(given) < seats:
        org = min(lines, key=lambda one: (holds[one], lines[one][0].asked_at, lines[one][0].room))
        given.append(lines[org].pop(0).room)
        holds[org] += 1
        if not lines[org]:
            del lines[org]
    return given
