"""The Studio tests' agenda: the clinic's API, served on the internet the suite's gateways reach."""

from collections.abc import Iterator

import httpx
import pytest

from tests.fakes.internet import Internet

AGENDA = "agenda.example.com"


@pytest.fixture
def agenda(internet: Internet) -> Iterator[list[httpx.Request]]:
    """The clinic's agenda, served on the internet the gateway reaches; the requests it was sent."""
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"patient": {"id": "p1", "name": "Ana Ruiz"}})

    with internet.serving(AGENDA, answer):
        yield seen
