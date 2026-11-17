"""A STUN message as a TURN relay speaks it: read off a datagram, written with its attributes, signed and checked."""

import hashlib
import hmac
import socket
import struct
from dataclasses import dataclass

# RFC 5389 §6: every message carries the cookie, which also masks the addresses it names.
COOKIE = 0x2112A442
HEADER = struct.Struct("!HHI12s")
ATTRIBUTE = struct.Struct("!HH")
# The first two bits of a STUN message are zero; of a ChannelData frame, 01 (RFC 5766 §11).
A_CHANNEL_FRAME = 0x40
CHANNEL = struct.Struct("!HH")

# The methods a relay answers (RFC 5389 §18.1, RFC 5766 §13), and the four classes of a message.
BINDING = 0x001
ALLOCATE = 0x003
REFRESH = 0x004
SEND = 0x006
DATA_INDICATION = 0x007
CREATE_PERMISSION = 0x008
CHANNEL_BIND = 0x009
REQUEST = 0x000
INDICATION = 0x010
SUCCESS = 0x100
FAILURE = 0x110
KINDS = REQUEST | INDICATION | SUCCESS | FAILURE

USERNAME = 0x0006
MESSAGE_INTEGRITY = 0x0008
ERROR_CODE = 0x0009
CHANNEL_NUMBER = 0x000C
LIFETIME = 0x000D
XOR_PEER_ADDRESS = 0x0012
DATA = 0x0013
REALM = 0x0014
NONCE = 0x0015
XOR_RELAYED_ADDRESS = 0x0016
XOR_MAPPED_ADDRESS = 0x0020

IPV4 = 0x01
# HMAC-SHA1's width: what MESSAGE-INTEGRITY carries.
SIGNATURE_BYTES = 20

type Address = tuple[str, int]


@dataclass(frozen=True, slots=True)
class Message:
    """One STUN message: its method and class, its transaction, its attributes in order, and its signature."""

    method: int
    kind: int
    transaction: bytes
    attributes: tuple[tuple[int, bytes], ...]
    # The datagram up to its MESSAGE-INTEGRITY, and the signature it carried; empty for an unsigned one.
    signed: bytes = b""
    signature: bytes = b""

    def find(self, attribute: int) -> bytes | None:
        """The first value of the attribute, or None."""
        return next((value for kind, value in self.attributes if kind == attribute), None)

    def list_of(self, attribute: int) -> list[bytes]:
        """Every value of the attribute, in the order sent."""
        return [value for kind, value in self.attributes if kind == attribute]

    def is_signed_by(self, key: bytes) -> bool:
        """Whether the message carries the signature this key makes of it."""
        if not self.signature:
            return False
        return hmac.compare_digest(_sign(self.signed, key), self.signature)


def is_a_channel_frame(datagram: bytes) -> bool:
    """Whether the datagram is a ChannelData frame and no STUN message."""
    return len(datagram) >= CHANNEL.size and datagram[0] & 0xC0 == A_CHANNEL_FRAME


def read_channel_frame(datagram: bytes) -> tuple[int, bytes] | None:
    """A ChannelData frame's channel and what it carries; None for one cut short."""
    number, length = CHANNEL.unpack_from(datagram)
    body = datagram[CHANNEL.size : CHANNEL.size + length]
    return (number, body) if len(body) == length else None


def write_channel_frame(number: int, body: bytes) -> bytes:
    """What a channel carries, framed: over UDP a frame is not padded (RFC 5766 §11.5)."""
    return CHANNEL.pack(number, len(body)) + body


# The signature covers the message up to its own attribute, with the header's length saying the
# signature is the last thing there (RFC 5389 §15.4): what follows it, a fingerprint, is not signed.
def read_message(datagram: bytes) -> Message | None:
    """The STUN message a datagram is; None for anything else."""
    if len(datagram) < HEADER.size or datagram[0] & 0xC0:
        return None
    kind, length, cookie, transaction = HEADER.unpack_from(datagram)
    if cookie != COOKIE or length % 4 or HEADER.size + length > len(datagram):
        return None
    attributes: list[tuple[int, bytes]] = []
    signed, signature = b"", b""
    at, end = HEADER.size, HEADER.size + length
    while at + ATTRIBUTE.size <= end:
        attribute, size = ATTRIBUTE.unpack_from(datagram, at)
        value = datagram[at + ATTRIBUTE.size : at + ATTRIBUTE.size + size]
        if len(value) != size:
            return None
        if attribute == MESSAGE_INTEGRITY and not signature:
            covered = at - HEADER.size + ATTRIBUTE.size + SIGNATURE_BYTES
            signed = HEADER.pack(kind, covered, cookie, transaction) + datagram[HEADER.size : at]
            signature = value
        attributes.append((attribute, value))
        at += ATTRIBUTE.size + size + (-size % 4)
    return Message(_method_of(kind), kind & KINDS, transaction, tuple(attributes), signed, signature)


def write_message(
    method: int, kind: int, transaction: bytes, attributes: list[tuple[int, bytes]], key: bytes | None = None
) -> bytes:
    """A STUN message of these attributes, signed last when a key is given."""
    body = b"".join(
        ATTRIBUTE.pack(attribute, len(value)) + value + b"\x00" * (-len(value) % 4) for attribute, value in attributes
    )
    if key is None:
        return HEADER.pack(method | kind, len(body), COOKIE, transaction) + body
    covered = len(body) + ATTRIBUTE.size + SIGNATURE_BYTES
    head = HEADER.pack(method | kind, covered, COOKIE, transaction) + body
    return head + ATTRIBUTE.pack(MESSAGE_INTEGRITY, SIGNATURE_BYTES) + _sign(head, key)


# RFC 5389 §15.4: the key of a long-term credential.
def key_of(username: str, realm: str, password: str) -> bytes:
    """The key a long-term credential signs with."""
    return hashlib.md5(f"{username}:{realm}:{password}".encode(), usedforsecurity=False).digest()


def write_address(address: Address) -> bytes:
    """An IPv4 address as an XOR-… attribute carries it."""
    host, port = address
    masked = struct.unpack("!I", socket.inet_aton(host))[0] ^ COOKIE
    return struct.pack("!BBHI", 0, IPV4, port ^ (COOKIE >> 16), masked)


def read_address(value: bytes) -> Address | None:
    """The IPv4 address an XOR-… attribute carries; None for another family."""
    if len(value) != 8 or value[1] != IPV4:
        return None
    port, masked = struct.unpack_from("!HI", value, 2)
    return socket.inet_ntoa(struct.pack("!I", masked ^ COOKIE)), port ^ (COOKIE >> 16)


def write_error(code: int, reason: str) -> bytes:
    """An ERROR-CODE's value: the class, the number, the words."""
    return struct.pack("!HBB", 0, code // 100, code % 100) + reason.encode()


def write_seconds(seconds: int) -> bytes:
    """A LIFETIME's value."""
    return struct.pack("!I", seconds)


def read_seconds(value: bytes | None) -> int | None:
    """The seconds a LIFETIME names; None when it names none."""
    return None if value is None or len(value) != 4 else int(struct.unpack("!I", value)[0])


def read_channel_number(value: bytes | None) -> int | None:
    """The channel a CHANNEL-NUMBER names; None when it names none."""
    return None if value is None or len(value) != 4 else int(struct.unpack_from("!H", value)[0])


# RFC 5389 §6: the class's two bits sit between the method's, at bits 4 and 8.
def _method_of(kind: int) -> int:
    return (kind & 0x000F) | ((kind & 0x00E0) >> 1) | ((kind & 0x3E00) >> 2)


def _sign(covered: bytes, key: bytes) -> bytes:
    return hmac.new(key, covered, hashlib.sha1).digest()
