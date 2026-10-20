"""What `setup` refuses before anything is brought up, and the server a run after the first keeps."""

import asyncio

import pytest

from pinecall_runtime.cli import setup
from pinecall_runtime.cli import setup_server as server_
from pinecall_runtime.exceptions import ValidationError

NAME = "voice.example.com"


def server_of(
    before: dict[str, str], *, domain: str | None = None, livekit: str | None = None, phone: bool = False
) -> server_.Server | None:
    return asyncio.run(setup.server_for(domain, livekit, None, False, phone, before, asking=False))


def test_a_laptop_runs_no_livekit_of_yours_and_no_phone() -> None:
    """LiveKit must reach the runtime and a laptop has no public address; the phone is a server's."""
    with pytest.raises(ValidationError, match="a laptop has no public address"):
        server_of({}, livekit="wss://acme.livekit.cloud")
    with pytest.raises(ValidationError, match="--phone is a server's"):
        server_of({}, phone=True)
    assert server_of({}) is None


def test_a_server_run_again_with_nothing_keeps_its_name_livekit_and_phone() -> None:
    """`setup` alone on a server is the server again: the update path needs no flag."""
    before = {"PINECALL_DOMAIN": NAME, "LIVEKIT_URL": "ws://127.0.0.1:7880", "PINECALL_SIP_DOMAIN": NAME}
    assert server_of(before) == server_.Server(NAME, None, phone=True)


def test_their_livekit_asks_for_its_pair_and_carries_no_phone() -> None:
    """With nobody to ask, a LiveKit of yours needs its key on the line; its phone is its own SIP's."""
    with pytest.raises(ValidationError, match="--livekit-key"):
        server_of({}, domain=NAME, livekit="wss://acme.livekit.cloud")
    theirs = {
        "PINECALL_DOMAIN": NAME,
        "LIVEKIT_URL": "wss://acme.livekit.cloud",
        "LIVEKIT_API_KEY": "k",
        "LIVEKIT_API_SECRET": "s",
    }
    with pytest.raises(ValidationError, match="that LiveKit's SIP"):
        server_of(theirs, phone=True)


def test_their_livekit_is_given_back_for_the_one_setup_starts() -> None:
    """`--livekit here` on a server running a LiveKit of yours puts setup's own back, the name kept."""
    theirs = {
        "PINECALL_DOMAIN": NAME,
        "LIVEKIT_URL": "wss://acme.livekit.cloud",
        "LIVEKIT_API_KEY": "k",
        "LIVEKIT_API_SECRET": "s",
    }
    assert server_of(theirs, livekit=server_.HERE) == server_.Server(NAME)
