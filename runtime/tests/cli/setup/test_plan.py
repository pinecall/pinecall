"""What `setup` refuses before anything is brought up, and the server a run after the first keeps."""

from pathlib import Path

import pytest

from runtime.cli.setup import server as server_
from runtime.cli.setup.plan import Flags, server_for
from runtime.exceptions import ValidationError

NAME = "voice.example.com"


async def server_of(
    before: dict[str, str], *, domain: str | None = None, livekit: str | None = None, phone: bool = False
) -> server_.Server | None:
    flags = Flags(
        where=Path("unused"),
        domain=domain,
        livekit=livekit,
        phone=phone,
        livekit_key=None,
        livekit_secret_stdin=False,
        wheel=None,
        email=None,
        person=None,
        password_stdin=False,
        asking=False,
        models=None,
        stt=None,
        turn=None,
        llm=None,
        tts=None,
        judge=None,
        caller=None,
        chat_only=False,
        services_only=False,
    )
    return await server_for(flags, before)


async def test_a_laptop_runs_no_livekit_of_yours_and_no_phone() -> None:
    """LiveKit must reach the runtime and a laptop has no public address; the phone is a server's."""
    with pytest.raises(ValidationError, match="a laptop has no public address"):
        await server_of({}, livekit="wss://acme.livekit.cloud")
    with pytest.raises(ValidationError, match="--phone is a server's"):
        await server_of({}, phone=True)
    assert await server_of({}) is None


async def test_a_server_run_again_with_nothing_keeps_its_name_livekit_and_phone() -> None:
    """`setup` alone on a server is the server again: the update path needs no flag."""
    before = {"PINECALL_DOMAIN": NAME, "LIVEKIT_URL": "ws://127.0.0.1:7880", "PINECALL_SIP_DOMAIN": NAME}
    assert await server_of(before) == server_.Server(NAME, None, phone=True)


async def test_their_livekit_asks_for_its_pair_and_carries_no_phone() -> None:
    """With nobody to ask, a LiveKit of yours needs its key on the line; its phone is its own SIP's."""
    with pytest.raises(ValidationError, match="--livekit-key"):
        await server_of({}, domain=NAME, livekit="wss://acme.livekit.cloud")
    theirs = {
        "PINECALL_DOMAIN": NAME,
        "LIVEKIT_URL": "wss://acme.livekit.cloud",
        "LIVEKIT_API_KEY": "k",
        "LIVEKIT_API_SECRET": "s",
    }
    with pytest.raises(ValidationError, match="that LiveKit's SIP"):
        await server_of(theirs, phone=True)


async def test_their_livekit_is_given_back_for_the_one_setup_starts() -> None:
    """`--livekit here` on a server running a LiveKit of yours puts setup's own back, the name kept."""
    theirs = {
        "PINECALL_DOMAIN": NAME,
        "LIVEKIT_URL": "wss://acme.livekit.cloud",
        "LIVEKIT_API_KEY": "k",
        "LIVEKIT_API_SECRET": "s",
    }
    assert await server_of(theirs, livekit=server_.HERE) == server_.Server(NAME)


def test_help_shows_a_persons_three_flags_and_help_all_the_scripts_under_their_heading() -> None:
    """A person reads --domain, --livekit and --phone; a script finds every answer under its own section."""
    from typer.testing import CliRunner

    from runtime.cli import app

    short = CliRunner().invoke(app, ["setup", "--help"]).output
    assert "--domain" in short and "--email" not in short
    long = CliRunner().invoke(app, ["setup", "--help-all"]).output
    assert "For a script" in long and "--email <str>" in long and "-y, --yes" in long
    assert long.index("--domain") < long.index("For a script") < long.index("--email")
