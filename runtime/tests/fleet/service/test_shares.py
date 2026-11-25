"""Whose turn a freed seat is: the org that holds the fewest goes first, then the caller that waited longest."""

from runtime.fleet.service.shares import Waiting, list_next


def a_line(org: str, callers: int, *, since: float) -> list[Waiting]:
    """An org's callers in the line, a second apart from `since`, named `<org>-<n>`."""
    return [Waiting(f"{org}-{at}", org, since + at) for at in range(callers)]


# 2026-11-25: one org's comparison held the six seats a waiting caller may take on production's
# sandbox, and every call another org placed waited behind the comparison's own.
def test_two_orgs_that_ask_at_once_are_seated_in_turn() -> None:
    waiting = [*a_line("acme", 4, since=100.0), *a_line("bolt", 4, since=100.5)]
    assert list_next(waiting, {}, 6) == ["acme-0", "bolt-0", "acme-1", "bolt-1", "acme-2", "bolt-2"]


def test_an_org_alone_in_the_line_takes_every_seat_there_is() -> None:
    waiting = a_line("acme", 8, since=100.0)
    assert list_next(waiting, {}, 6) == [f"acme-{at}" for at in range(6)]
    assert list_next(waiting, {"acme": 6}, 2) == ["acme-0", "acme-1"], "nothing is held back for an org not asking"


def test_an_org_that_arrives_while_another_holds_every_seat_is_given_the_next_ones_that_free() -> None:
    waiting = [*a_line("acme", 4, since=100.0), *a_line("bolt", 3, since=500.0)]
    held = {"acme": 6}
    assert list_next(waiting, held, 1) == ["bolt-0"], "the caller that asked last, of the org that holds none"
    # Seats free one by one as acme's calls end: bolt's callers take them until the two hold the same.
    given: list[str] = []
    for _ in range(4):
        held["acme"] -= 1
        room = list_next([one for one in waiting if one.room not in given], held, 1)[0]
        given.append(room)
        held[room.split("-")[0]] = held.get(room.split("-")[0], 0) + 1
    assert given == ["bolt-0", "bolt-1", "bolt-2", "acme-0"]
    assert held == {"acme": 3, "bolt": 3}


def test_three_orgs_come_to_a_third_each() -> None:
    waiting = [*a_line("acme", 6, since=100.0), *a_line("bolt", 6, since=101.0), *a_line("cord", 6, since=102.0)]
    given = list_next(waiting, {}, 6)
    assert sorted(room.split("-")[0] for room in given) == ["acme", "acme", "bolt", "bolt", "cord", "cord"]


def test_among_orgs_that_hold_the_same_and_among_an_orgs_own_the_longest_wait_goes_first() -> None:
    waiting = [Waiting("late", "acme", 300.0), Waiting("early", "acme", 100.0), Waiting("other", "bolt", 200.0)]
    assert list_next(waiting, {"acme": 2, "bolt": 2}, 3) == ["early", "other", "late"]
    assert list_next(waiting, {"acme": 2, "bolt": 4}, 2) == ["early", "late"], "bolt holds more than acme would"


def test_no_seat_goes_to_nobody_and_a_line_shorter_than_the_seats_is_seated_whole() -> None:
    assert list_next(a_line("acme", 2, since=100.0), {}, 0) == []
    assert list_next(a_line("acme", 2, since=100.0), {}, 5) == ["acme-0", "acme-1"]
    assert list_next([], {"acme": 3}, 5) == []
