"""`setup`'s questions, awaited on the loop that asks them, as `carry_out` does on its verb's."""

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from runtime.cli.setup import ask


async def test_the_console_persons_email_is_asked_on_the_running_loop() -> None:
    """The address typed comes back trimmed: a question starts no loop of its own inside setup's."""
    with create_pipe_input() as typed, create_app_session(input=typed, output=DummyOutput()):
        typed.send_text(" ana@example.com \r")
        assert await ask.email() == "ana@example.com"


async def test_the_password_is_asked_again_until_the_two_agree() -> None:
    """Two that differ are asked once more; the pair that agrees is the password, as it was typed."""
    with create_pipe_input() as typed, create_app_session(input=typed, output=DummyOutput()):
        typed.send_text("first\rother\r se cret \r se cret \r")
        assert await ask.password() == " se cret "


async def test_a_key_and_a_livekit_pair_are_typed_and_trimmed() -> None:
    """A vendor's key found nowhere, and the pair of the operator's own LiveKit: each one line, trimmed."""
    with create_pipe_input() as typed, create_app_session(input=typed, output=DummyOutput()):
        typed.send_text(" sk-typed \r APIacme \r their-secret \r")
        assert await ask.secret("ACME_API_KEY") == "sk-typed"
        assert await ask.livekit_key() == "APIacme"
        assert await ask.livekit_secret() == "their-secret"
