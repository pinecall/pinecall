"""Who may read `/metrics`: the addresses the box names, and never a request a proxy passed on."""

import pytest

from runtime.exceptions import Forbidden
from runtime.platform.service.metrics import check_reader, is_from_any, read_metrics


def test_an_address_is_one_the_box_names_or_inside_a_network_it_names() -> None:
    assert is_from_any("127.0.0.1", "127.0.0.1,::1")
    assert is_from_any("::1", "127.0.0.1,::1")
    assert is_from_any("10.4.0.17", "10.0.0.0/8")
    assert not is_from_any("203.0.113.9", "127.0.0.1,10.0.0.0/8")
    assert not is_from_any("not an address", "127.0.0.1")


def test_a_forwarded_request_is_refused_whatever_address_it_came_from() -> None:
    check_reader("127.0.0.1", False, "127.0.0.1")
    with pytest.raises(Forbidden, match="never a forwarded request"):
        check_reader("127.0.0.1", True, "127.0.0.1")
    with pytest.raises(Forbidden):
        check_reader("203.0.113.9", False, "127.0.0.1")


class Saying:
    """An owner that says one line."""

    def __init__(self, line: str) -> None:
        self.line = line

    async def collect(self, now: float) -> str:
        """Its line, whatever the moment."""
        del now
        return self.line


async def test_every_owners_families_are_read_in_the_order_the_process_lists_them() -> None:
    assert await read_metrics((Saying("a 1\n"), Saying("b 2\n")), 0.0) == "a 1\nb 2\n"
