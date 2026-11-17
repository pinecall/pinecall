"""A TURN relay on this machine's loopback: one client's packets cross it, each way through a link of its own."""

import asyncio
import contextlib
import logging
import random as randomness
import secrets
import socket
from dataclasses import dataclass, field
from typing import Any, override

from runtime.kit import stun
from runtime.kit.link import Link, LinkShape

logger = logging.getLogger(__name__)

LOOPBACK = "127.0.0.1"
REALM = "relay"
USERNAME = "client"
# RFC 5766 §2.2: an allocation lives ten minutes from its last refresh.
LIFETIME_S = 600
# RFC 5766 §11: the numbers a client may bind a channel under.
FIRST_CHANNEL = 0x4000
LAST_CHANNEL = 0x7FFF
# An address of TEST-NET-1 (RFC 5737): nothing is sent to it, the routing table is only asked the way out.
A_FAR_ADDRESS = ("192.0.2.1", 9)

BAD_REQUEST = (400, "Bad Request")
UNAUTHORIZED = (401, "Unauthorized")
NO_ALLOCATION = (437, "Allocation Mismatch")
ANOTHER_FAMILY = (443, "Peer Address Family Mismatch")


@dataclass(slots=True)
class Allocation:
    """What the relay holds for its client: the socket its peers reach, whom it hears from, the channels bound."""

    transport: asyncio.DatagramTransport
    relayed: stun.Address
    # The transaction that made it: the request said again is answered again.
    made_by: bytes
    permitted: set[str] = field(default_factory=set[str])
    channel_of: dict[stun.Address, int] = field(default_factory=dict[stun.Address, int])
    peer_of: dict[int, stun.Address] = field(default_factory=dict[int, stun.Address])


# A WebRTC client told this relay is its only ICE server, and to use relays alone, sends every packet
# of its call through this process: the one place a line's loss, delay and rate can be set without a
# root's `tc`, the same on every machine. The relay listens on
# the loopback, with a pair of its own drawn at each start, so nothing outside the machine reaches it;
# the socket its peers answer on is the machine's way out. What the client sends crosses `uplink`, what
# its peers answer crosses `downlink`: the ICE checks and the RTCP with the media, as on a real path.
class Relay:
    """A TURN relay for one client on this machine, shaping what it carries each way."""

    def __init__(self, shape: LinkShape, dice: randomness.Random | None = None) -> None:
        self.username = USERNAME
        self.password = secrets.token_hex(16)
        self.uplink = Link(shape, dice)
        self.downlink = Link(shape, dice)
        self._key = stun.key_of(self.username, REALM, self.password)
        self._nonce = secrets.token_hex(8).encode()
        self._transport: asyncio.DatagramTransport | None = None
        self._allocations: dict[stun.Address, Allocation] = {}
        self._opening: dict[stun.Address, asyncio.Task[None]] = {}

    async def open(self) -> None:
        """Start listening on a port of the loopback."""
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(lambda: _ClientSide(self), local_addr=(LOOPBACK, 0))

    async def close(self) -> None:
        """Stop listening, and let every allocation go."""
        for opening in list(self._opening.values()):
            opening.cancel()
        await asyncio.gather(*self._opening.values(), return_exceptions=True)
        for allocation in self._allocations.values():
            allocation.transport.close()
        self._allocations.clear()
        if self._transport is not None:
            self._transport.close()

    @property
    def url(self) -> str:
        """The relay as an ICE server's URL."""
        if self._transport is None:
            raise RuntimeError("the relay is not open: it has no port yet")
        port = self._transport.get_extra_info("sockname")[1]
        return f"turn:{LOOPBACK}:{port}?transport=udp"

    def hear_client(self, datagram: bytes, client: stun.Address) -> None:
        """Take one datagram of the client's: a channel's frame, an indication, or a request to answer."""
        if stun.is_a_channel_frame(datagram):
            self._carry_frame(datagram, client)
            return
        message = stun.read_message(datagram)
        if message is None:
            return
        if message.kind == stun.INDICATION:
            self._carry_indication(message, client)
        elif message.kind == stun.REQUEST:
            self._answer(message, client)

    def hear_peer(self, datagram: bytes, peer: stun.Address, client: stun.Address) -> None:
        """Take one datagram a peer sent the client's allocation, and carry it down to the client."""
        allocation = self._allocations.get(client)
        if allocation is None or peer[0] not in allocation.permitted:
            return
        number = allocation.channel_of.get(peer)
        if number is not None:
            framed = stun.write_channel_frame(number, datagram)
        else:
            said = [(stun.XOR_PEER_ADDRESS, stun.write_address(peer)), (stun.DATA, datagram)]
            framed = stun.write_message(stun.DATA_INDICATION, stun.INDICATION, secrets.token_bytes(12), said)
        self.downlink.carry(framed, lambda packet: self._send(packet, client))

    # ── the client's requests ──

    # RFC 5766 §4: the first request of a client carries no credential and is answered with the realm
    # and a nonce; every one after it is signed with the long-term key, and so is its answer.
    def _answer(self, message: stun.Message, client: stun.Address) -> None:
        if message.method == stun.BINDING:
            mapped = [(stun.XOR_MAPPED_ADDRESS, stun.write_address(client))]
            self._send(stun.write_message(stun.BINDING, stun.SUCCESS, message.transaction, mapped), client)
            return
        if not message.is_signed_by(self._key):
            challenge = [(stun.REALM, REALM.encode()), (stun.NONCE, self._nonce)]
            self._refuse(message, client, UNAUTHORIZED, challenge, signed=False)
            return
        if message.method == stun.ALLOCATE:
            self._allocate(message, client)
            return
        allocation = self._allocations.get(client)
        if allocation is None:
            self._refuse(message, client, NO_ALLOCATION)
        elif message.method == stun.REFRESH:
            self._refresh(message, client, allocation)
        elif message.method == stun.CREATE_PERMISSION:
            self._permit(message, client, allocation)
        elif message.method == stun.CHANNEL_BIND:
            self._bind(message, client, allocation)
        else:
            self._refuse(message, client, BAD_REQUEST)

    def _allocate(self, message: stun.Message, client: stun.Address) -> None:
        existing = self._allocations.get(client)
        if existing is not None and existing.made_by != message.transaction:
            self._refuse(message, client, NO_ALLOCATION)
        elif existing is not None:
            self._say_allocated(message, client, existing)
        elif client not in self._opening:
            opening = asyncio.ensure_future(self._open_allocation(message, client))
            self._opening[client] = opening
            opening.add_done_callback(lambda _: self._opening.pop(client, None))

    async def _open_allocation(self, message: stun.Message, client: stun.Address) -> None:
        loop = asyncio.get_running_loop()
        out = find_way_out()
        transport, _ = await loop.create_datagram_endpoint(lambda: _PeerSide(self, client), local_addr=(out, 0))
        relayed = (out, int(transport.get_extra_info("sockname")[1]))
        allocation = self._allocations[client] = Allocation(transport, relayed, message.transaction)
        self._say_allocated(message, client, allocation)

    def _say_allocated(self, message: stun.Message, client: stun.Address, allocation: Allocation) -> None:
        said = [
            (stun.XOR_RELAYED_ADDRESS, stun.write_address(allocation.relayed)),
            (stun.XOR_MAPPED_ADDRESS, stun.write_address(client)),
            (stun.LIFETIME, stun.write_seconds(LIFETIME_S)),
        ]
        self._succeed(message, client, said)

    # A lifetime of zero is the client leaving (RFC 5766 §7).
    def _refresh(self, message: stun.Message, client: stun.Address, allocation: Allocation) -> None:
        asked = stun.read_seconds(message.find(stun.LIFETIME))
        lifetime = LIFETIME_S if asked is None else min(asked, LIFETIME_S)
        if lifetime == 0:
            allocation.transport.close()
            del self._allocations[client]
        self._succeed(message, client, [(stun.LIFETIME, stun.write_seconds(lifetime))])

    def _permit(self, message: stun.Message, client: stun.Address, allocation: Allocation) -> None:
        peers = [stun.read_address(value) for value in message.list_of(stun.XOR_PEER_ADDRESS)]
        if not peers:
            self._refuse(message, client, BAD_REQUEST)
        elif None in peers:
            self._refuse(message, client, ANOTHER_FAMILY)
        else:
            allocation.permitted.update(peer[0] for peer in peers if peer is not None)
            self._succeed(message, client, [])

    # RFC 5766 §11.2: a channel names one peer and a peer one channel, for as long as the allocation.
    def _bind(self, message: stun.Message, client: stun.Address, allocation: Allocation) -> None:
        number = stun.read_channel_number(message.find(stun.CHANNEL_NUMBER))
        value = message.find(stun.XOR_PEER_ADDRESS)
        peer = None if value is None else stun.read_address(value)
        if number is None or peer is None or not FIRST_CHANNEL <= number <= LAST_CHANNEL:
            self._refuse(message, client, BAD_REQUEST)
            return
        if allocation.peer_of.get(number, peer) != peer or allocation.channel_of.get(peer, number) != number:
            self._refuse(message, client, BAD_REQUEST)
            return
        allocation.peer_of[number] = peer
        allocation.channel_of[peer] = number
        allocation.permitted.add(peer[0])
        self._succeed(message, client, [])

    # ── what the client sends its peers ──

    def _carry_indication(self, message: stun.Message, client: stun.Address) -> None:
        allocation = self._allocations.get(client)
        value, data = message.find(stun.XOR_PEER_ADDRESS), message.find(stun.DATA)
        peer = None if value is None else stun.read_address(value)
        if message.method == stun.SEND and allocation is not None and peer is not None and data is not None:
            self._carry_up(allocation, peer, data)

    def _carry_frame(self, datagram: bytes, client: stun.Address) -> None:
        allocation = self._allocations.get(client)
        frame = stun.read_channel_frame(datagram)
        if allocation is None or frame is None:
            return
        peer = allocation.peer_of.get(frame[0])
        if peer is not None:
            self._carry_up(allocation, peer, frame[1])

    def _carry_up(self, allocation: Allocation, peer: stun.Address, data: bytes) -> None:
        if peer[0] not in allocation.permitted:
            return

        def deliver(packet: bytes) -> None:
            if not allocation.transport.is_closing():
                allocation.transport.sendto(packet, peer)

        self.uplink.carry(data, deliver)

    # ── private ──

    def _succeed(self, message: stun.Message, client: stun.Address, said: list[tuple[int, bytes]]) -> None:
        self._send(stun.write_message(message.method, stun.SUCCESS, message.transaction, said, self._key), client)

    def _refuse(
        self,
        message: stun.Message,
        client: stun.Address,
        why: tuple[int, str],
        more: list[tuple[int, bytes]] | None = None,
        *,
        signed: bool = True,
    ) -> None:
        said = [(stun.ERROR_CODE, stun.write_error(*why)), *(more or [])]
        key = self._key if signed else None
        self._send(stun.write_message(message.method, stun.FAILURE, message.transaction, said, key), client)

    def _send(self, datagram: bytes, client: stun.Address) -> None:
        if self._transport is not None and not self._transport.is_closing():
            self._transport.sendto(datagram, client)


# Nothing is sent: connecting a datagram socket only asks the routing table which address leaves.
def find_way_out() -> str:
    """The address this machine reaches the network from; the loopback when it has no way out."""
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as probe:
        try:
            probe.connect(A_FAR_ADDRESS)
        except OSError:
            return LOOPBACK
        return str(probe.getsockname()[0])


class _ClientSide(asyncio.DatagramProtocol):
    def __init__(self, relay: Relay) -> None:
        self._relay = relay

    @override
    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self._relay.hear_client(data, (str(addr[0]), addr[1]))


class _PeerSide(asyncio.DatagramProtocol):
    def __init__(self, relay: Relay, client: stun.Address) -> None:
        self._relay = relay
        self._client = client

    @override
    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self._relay.hear_peer(data, (str(addr[0]), addr[1]), self._client)
