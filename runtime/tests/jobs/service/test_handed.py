"""The sentence a developer hears while their ring crosses to the sandbox never keeps the ring from crossing."""

from typing import cast

import httpx
from livekit.agents import JobContext

from runtime.actor import Scope
from runtime.enums import Env
from runtime.jobs.service.client import GatewayClient
from runtime.jobs.service.handed import HANDED_SAYS, tell_it_is_handed


class ARoom:
    """A room that only has a name: nothing is said in it before the voice is had."""

    name = "call-_+15550199_abc"


class AJob:
    """A job in that room."""

    room = ARoom()


def refusing(asked: list[str]) -> GatewayClient:
    """The worker's own client, on a gateway that has no voice to give."""

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return httpx.Response(503, json={"detail": "no key for this voice"})

    return GatewayClient(httpx.AsyncClient(base_url="http://gateway.test", transport=httpx.MockTransport(answer)))


async def test_a_voice_that_cannot_be_had_says_nothing_and_raises_nothing() -> None:
    asked: list[str] = []
    await tell_it_is_handed(cast("JobContext", AJob()), refusing(asked), "front", Scope("org_a", Env.production))
    assert asked == ["/v1/agents/front/provider-keys"]


def test_the_sentence_says_where_the_ring_is_going() -> None:
    assert "sandbox" in HANDED_SAYS
