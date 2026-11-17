"""A TURN relay on the loopback, asked as a WebRTC client asks it: the challenge, an allocation, both ways through."""

import asyncio
import secrets
from collections.abc import AsyncIterator
from typing import Any, override

import pytest

from runtime.kit import stun
from runtime.kit.link import LinkShape
from runtime.kit.turn import LIFETIME_S, LOOPBACK, REALM, Relay

HEARD_WITHIN_S = 2.0
A_CHANNEL = 0x4000


class Socket(asyncio.DatagramProtocol):
    """A datagram socket on the loopback that keeps what it hears, and from whom."""

    def __init__(self) -> None:
        self.heard: asyncio.Queue[tuple[bytes, stun.Address]] = asyncio.Queue()
        self.transport: asyncio.DatagramTransport | None = None

    @classmethod
    async def open(cls) -> "Socket":
        made = cls()
        loop = asyncio.get_running_loop()
        made.transport, _ = await loop.create_datagram_endpoint(lambda: made, local_addr=(LOOPBACK, 0))
        return made

    @property
    def address(self) -> stun.Address:
        assert self.transport is not None
        host, port = self.transport.get_extra_info("sockname")[:2]
        return str(host), int(port)

    def send(self, datagram: bytes, to: stun.Address) -> None:
        assert self.transport is not None
        self.transport.sendto(datagram, to)

    async def hear(self) -> tuple[bytes, stun.Address]:
        return await asyncio.wait_for(self.heard.get(), HEARD_WITHIN_S)

    async def hears_nothing(self, within_s: float = 0.2) -> bool:
        try:
            await asyncio.wait_for(self.heard.get(), within_s)
        except TimeoutError:
            return True
        return False

    def close(self) -> None:
        assert self.transport is not None
        self.transport.close()

    @override
    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self.heard.put_nowait((data, (str(addr[0]), addr[1])))


class Client:
    """A TURN client as libwebrtc is one: a request, its answer, an indication, a channel's frame."""

    def __init__(self, socket: Socket, relay: Relay, password: str | None = None) -> None:
        self.socket = socket
        self.relay = relay
        self.to = (LOOPBACK, int(relay.url.split(":")[2].split("?")[0]))
        self.key = stun.key_of(relay.username, REALM, password or relay.password)

    async def ask(self, method: int, said: list[tuple[int, bytes]], *, signed: bool = True) -> stun.Message:
        request = stun.write_message(method, stun.REQUEST, secrets.token_bytes(12), said, self.key if signed else None)
        self.socket.send(request, self.to)
        answer = stun.read_message((await self.socket.hear())[0])
        assert answer is not None
        return answer

    async def allocate(self) -> stun.Address:
        answer = await self.ask(stun.ALLOCATE, [])
        assert answer.kind == stun.SUCCESS
        relayed = stun.read_address(answer.find(stun.XOR_RELAYED_ADDRESS) or b"")
        assert relayed is not None
        return relayed

    async def permit(self, peer: stun.Address) -> stun.Message:
        return await self.ask(stun.CREATE_PERMISSION, [(stun.XOR_PEER_ADDRESS, stun.write_address(peer))])

    def send_to(self, peer: stun.Address, data: bytes) -> None:
        said = [(stun.XOR_PEER_ADDRESS, stun.write_address(peer)), (stun.DATA, data)]
        self.socket.send(stun.write_message(stun.SEND, stun.INDICATION, secrets.token_bytes(12), said), self.to)


@pytest.fixture
async def sockets() -> AsyncIterator[tuple[Socket, Socket]]:
    """The client's socket and a peer's, both closed after."""
    client, peer = await Socket.open(), await Socket.open()
    try:
        yield client, peer
    finally:
        client.close()
        peer.close()


async def a_relay(shape: LinkShape | None = None) -> Relay:
    relay = Relay(shape or LinkShape())
    await relay.open()
    return relay


async def test_a_request_with_no_credential_is_challenged_with_the_realm_and_a_nonce(
    sockets: tuple[Socket, Socket],
) -> None:
    relay = await a_relay()
    answer = await Client(sockets[0], relay).ask(stun.ALLOCATE, [], signed=False)
    assert (answer.method, answer.kind) == (stun.ALLOCATE, stun.FAILURE)
    assert (answer.find(stun.ERROR_CODE) or b"")[2:4] == b"\x04\x01"
    assert answer.find(stun.REALM) == REALM.encode()
    assert answer.find(stun.NONCE)
    await relay.close()


async def test_a_request_signed_with_another_password_is_challenged_again(sockets: tuple[Socket, Socket]) -> None:
    relay = await a_relay()
    answer = await Client(sockets[0], relay, password="not the relay's").ask(stun.ALLOCATE, [])
    assert answer.kind == stun.FAILURE
    await relay.close()


async def test_an_allocation_answers_where_peers_reach_it_who_asked_and_for_how_long(
    sockets: tuple[Socket, Socket],
) -> None:
    relay = await a_relay()
    client = Client(sockets[0], relay)
    answer = await client.ask(stun.ALLOCATE, [])
    assert answer.kind == stun.SUCCESS
    assert answer.is_signed_by(client.key), "libwebrtc drops an answer its key did not sign"
    assert stun.read_address(answer.find(stun.XOR_MAPPED_ADDRESS) or b"") == sockets[0].address
    assert stun.read_address(answer.find(stun.XOR_RELAYED_ADDRESS) or b"") is not None
    assert stun.read_seconds(answer.find(stun.LIFETIME)) == LIFETIME_S
    await relay.close()


async def test_a_second_allocation_of_the_same_client_is_refused(sockets: tuple[Socket, Socket]) -> None:
    relay = await a_relay()
    client = Client(sockets[0], relay)
    await client.allocate()
    again = await client.ask(stun.ALLOCATE, [])
    assert (again.find(stun.ERROR_CODE) or b"")[2:4] == b"\x04\x25"
    await relay.close()


async def test_what_the_client_sends_a_permitted_peer_reaches_it_from_the_relayed_address_and_back(
    sockets: tuple[Socket, Socket],
) -> None:
    client_socket, peer = sockets
    relay = await a_relay()
    client = Client(client_socket, relay)
    relayed = await client.allocate()
    assert (await client.permit(peer.address)).kind == stun.SUCCESS
    client.send_to(peer.address, b"up")
    data, sender = await peer.hear()
    assert (data, sender[1]) == (b"up", relayed[1])
    peer.send(b"down", sender)
    indication = stun.read_message((await client_socket.hear())[0])
    assert indication is not None
    assert (indication.method, indication.kind) == (stun.DATA_INDICATION, stun.INDICATION)
    assert indication.find(stun.DATA) == b"down"
    assert stun.read_address(indication.find(stun.XOR_PEER_ADDRESS) or b"") == peer.address
    assert (relay.uplink.counts.carried, relay.downlink.counts.carried) == (1, 1)
    await relay.close()


async def test_a_peer_nobody_permitted_is_neither_sent_to_nor_heard(sockets: tuple[Socket, Socket]) -> None:
    client_socket, peer = sockets
    relay = await a_relay()
    client = Client(client_socket, relay)
    relayed = await client.allocate()
    client.send_to(peer.address, b"up")
    assert await peer.hears_nothing()
    peer.send(b"down", relayed)
    assert await client_socket.hears_nothing()
    await relay.close()


async def test_a_bound_channel_carries_frames_both_ways_with_no_message_around_them(
    sockets: tuple[Socket, Socket],
) -> None:
    client_socket, peer = sockets
    relay = await a_relay()
    client = Client(client_socket, relay)
    await client.allocate()
    number = (A_CHANNEL << 16).to_bytes(4, "big")
    bound = await client.ask(
        stun.CHANNEL_BIND, [(stun.CHANNEL_NUMBER, number), (stun.XOR_PEER_ADDRESS, stun.write_address(peer.address))]
    )
    assert bound.kind == stun.SUCCESS
    client_socket.send(stun.write_channel_frame(A_CHANNEL, b"up"), client.to)
    data, sender = await peer.hear()
    assert data == b"up"
    peer.send(b"down", sender)
    assert stun.read_channel_frame((await client_socket.hear())[0]) == (A_CHANNEL, b"down")
    await relay.close()


async def test_a_refresh_of_zero_lets_the_allocation_go(sockets: tuple[Socket, Socket]) -> None:
    relay = await a_relay()
    client = Client(sockets[0], relay)
    await client.allocate()
    left = await client.ask(stun.REFRESH, [(stun.LIFETIME, stun.write_seconds(0))])
    assert (left.kind, stun.read_seconds(left.find(stun.LIFETIME))) == (stun.SUCCESS, 0)
    after = await client.permit(sockets[1].address)
    assert (after.find(stun.ERROR_CODE) or b"")[2:4] == b"\x04\x25"
    await relay.close()


async def test_a_link_that_loses_everything_carries_nothing_up_and_counts_it(sockets: tuple[Socket, Socket]) -> None:
    client_socket, peer = sockets
    relay = await a_relay(LinkShape(loss=1.0))
    client = Client(client_socket, relay)
    await client.allocate()
    await client.permit(peer.address)
    for _ in range(5):
        client.send_to(peer.address, b"up")
    assert await peer.hears_nothing()
    assert (relay.uplink.counts.lost, relay.uplink.counts.carried) == (5, 0)
    await relay.close()


async def test_a_slow_link_holds_what_the_client_sends_before_the_peer_hears_it(sockets: tuple[Socket, Socket]) -> None:
    client_socket, peer = sockets
    relay = await a_relay(LinkShape(delay_ms=150))
    client = Client(client_socket, relay)
    await client.allocate()
    await client.permit(peer.address)
    began = asyncio.get_running_loop().time()
    client.send_to(peer.address, b"up")
    await peer.hear()
    assert asyncio.get_running_loop().time() - began >= 0.14
    await relay.close()
