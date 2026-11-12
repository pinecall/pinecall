"""The internet as the suite's gateways reach it: a host a test serves under a name of its own, the network else."""

import ipaddress
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import override

import httpx

from runtime.handles import Outside
from runtime.kit import dns

# What a name a test serves resolves to: an address on the public internet, as a business's API has.
A_PUBLIC_ADDRESS = ipaddress.ip_address("93.184.216.34")

type Answer = Callable[[httpx.Request], httpx.Response]


class Internet(httpx.AsyncBaseTransport):
    """Where a gateway's requests go: a host a test serves answers as that test says; any other, the network."""

    def __init__(self) -> None:
        """Serving nothing of its own yet."""
        self.served: dict[str, Answer] = {}
        self.network = httpx.AsyncHTTPTransport()

    @contextmanager
    def serving(self, host: str, answer: Answer) -> Generator[None]:
        """Answer every request to this host with `answer` for as long as the block runs."""
        self.served[host] = answer
        try:
            yield
        finally:
            del self.served[host]

    def resolve(self, host: str) -> list[dns.Address]:
        """A host served here is public; any other name, as the box's DNS says."""
        return [A_PUBLIC_ADDRESS] if host in self.served else dns.resolve(host)

    @override
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """The served host's answer, or the network's."""
        answer = self.served.get(request.url.host)
        if answer is None:
            return await self.network.handle_async_request(request)
        await request.aread()
        return answer(request)

    @override
    async def aclose(self) -> None:
        """Close the network's connections."""
        await self.network.aclose()

    @property
    def outside(self) -> Outside:
        """This internet, as a gateway is handed what it reaches."""
        return Outside(transport=self, resolve=self.resolve)
