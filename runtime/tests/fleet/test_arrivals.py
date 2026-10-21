"""A room's newest dispatch is a call to place only when it names a fleet."""

from pinecall_runtime.fleet.service.arrivals import names_a_fleet


def test_a_fleets_plain_name_is_a_call_to_place() -> None:
    """The SIP rule and a visitor's token dispatch to the fleet by its plain name."""
    assert names_a_fleet("pinecall")
    assert names_a_fleet("pinecall-sandbox")


def test_a_workers_name_is_the_gateways_own_dispatch_and_left_alone() -> None:
    """A worker registers as <fleet>/<worker>: a dispatch to it was the gateway's choice already."""
    assert not names_a_fleet("pinecall/worker-core-production-1")
    assert not names_a_fleet("pinecall/overflow")


def test_livekits_automatic_dispatch_names_nobody() -> None:
    """LiveKit's own dispatch names no agent; kept, it would be a room of no fleet (2026-10-21)."""
    assert not names_a_fleet("")
