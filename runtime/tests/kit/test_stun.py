"""A STUN message: written and read back, signed and checked, its addresses masked, a channel's frame."""

import secrets

from runtime.kit import stun

A_TRANSACTION = bytes(range(12))
A_KEY = stun.key_of("client", "relay", "a password")


def test_a_message_written_is_read_back_with_its_attributes_in_order() -> None:
    said = [(stun.REALM, b"relay"), (stun.NONCE, b"abcdef"), (stun.LIFETIME, stun.write_seconds(600))]
    read = stun.read_message(stun.write_message(stun.ALLOCATE, stun.SUCCESS, A_TRANSACTION, said))
    assert read is not None
    assert (read.method, read.kind, read.transaction) == (stun.ALLOCATE, stun.SUCCESS, A_TRANSACTION)
    assert list(read.attributes) == said
    assert stun.read_seconds(read.find(stun.LIFETIME)) == 600
    assert read.find(stun.DATA) is None


def test_every_method_a_relay_answers_survives_each_class() -> None:
    methods = (stun.BINDING, stun.ALLOCATE, stun.REFRESH, stun.SEND, stun.CREATE_PERMISSION, stun.CHANNEL_BIND)
    for method in methods:
        for kind in (stun.REQUEST, stun.INDICATION, stun.SUCCESS, stun.FAILURE):
            read = stun.read_message(stun.write_message(method, kind, A_TRANSACTION, []))
            assert read is not None
            assert (read.method, read.kind) == (method, kind)


def test_a_signed_message_is_signed_by_its_key_and_by_no_other() -> None:
    read = stun.read_message(stun.write_message(stun.ALLOCATE, stun.REQUEST, A_TRANSACTION, [], A_KEY))
    assert read is not None
    assert read.is_signed_by(A_KEY)
    assert not read.is_signed_by(stun.key_of("client", "relay", "another password"))


def test_an_unsigned_message_is_signed_by_nobody() -> None:
    read = stun.read_message(stun.write_message(stun.ALLOCATE, stun.REQUEST, A_TRANSACTION, []))
    assert read is not None
    assert not read.is_signed_by(A_KEY)


def test_a_message_changed_after_it_was_signed_no_longer_carries_its_signature() -> None:
    written = bytearray(stun.write_message(stun.REFRESH, stun.REQUEST, A_TRANSACTION, [(stun.REALM, b"relay")], A_KEY))
    written[stun.HEADER.size + stun.ATTRIBUTE.size] ^= 0xFF
    read = stun.read_message(bytes(written))
    assert read is not None
    assert not read.is_signed_by(A_KEY)


# RFC 5389 §15.4: what follows the signature, a fingerprint, is not what was signed.
def test_what_follows_the_signature_is_not_covered_by_it() -> None:
    signed = stun.write_message(stun.ALLOCATE, stun.REQUEST, A_TRANSACTION, [(stun.REALM, b"relay")], A_KEY)
    fingerprint = stun.ATTRIBUTE.pack(0x8028, 4) + b"\x01\x02\x03\x04"
    kind, length, cookie, transaction = stun.HEADER.unpack_from(signed)
    longer = stun.HEADER.pack(kind, length + len(fingerprint), cookie, transaction) + signed[stun.HEADER.size :]
    read = stun.read_message(longer + fingerprint)
    assert read is not None
    assert read.is_signed_by(A_KEY)
    assert read.find(0x8028) == b"\x01\x02\x03\x04"


def test_an_address_is_masked_on_the_wire_and_read_back_whole() -> None:
    written = stun.write_address(("203.0.113.7", 50123))
    assert b"\xcb\x00\x71\x07" not in written
    assert stun.read_address(written) == ("203.0.113.7", 50123)
    assert stun.read_address(b"\x00\x02" + bytes(18)) is None, "an IPv6 address is not one this relay carries"


def test_what_is_no_stun_message_is_read_as_nothing() -> None:
    written = stun.write_message(stun.BINDING, stun.REQUEST, A_TRANSACTION, [(stun.REALM, b"relay")])
    assert stun.read_message(b"") is None
    assert stun.read_message(secrets.token_bytes(8)) is None
    assert stun.read_message(written[:-3]) is None
    assert stun.read_message(written[:4] + b"\x00\x00\x00\x00" + written[8:]) is None, "no cookie"
    assert stun.read_message(b"\x80" + written[1:]) is None, "an RTP packet opens with other bits"


def test_a_channels_frame_is_told_from_a_message_and_carries_its_bytes() -> None:
    frame = stun.write_channel_frame(0x4001, b"an rtp packet")
    assert stun.is_a_channel_frame(frame)
    assert not stun.is_a_channel_frame(stun.write_message(stun.BINDING, stun.REQUEST, A_TRANSACTION, []))
    assert stun.read_channel_frame(frame) == (0x4001, b"an rtp packet")
    assert stun.read_channel_frame(frame[:-2]) is None


def test_an_error_says_its_class_its_number_and_its_words() -> None:
    assert stun.write_error(437, "Allocation Mismatch") == b"\x00\x00\x04\x25Allocation Mismatch"
    assert stun.read_channel_number(b"\x40\x01\x00\x00") == 0x4001
    assert stun.read_channel_number(None) is None
