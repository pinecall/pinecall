"""What `setup` asks at a terminal: a key found nowhere, the console's person, the pair of a LiveKit of yours."""

import typer
from prompt_toolkit import PromptSession


# `setup` runs on its verb's loop, so a question is awaited on that loop. prompt_toolkit's `prompt()`
# starts a loop of its own, which Python refuses inside one that runs: until 2026-11-16 the first
# question ended setup with a traceback, and no test asked one from inside a loop.
async def _ask(message: str, *, hidden: bool = False) -> str:
    session: PromptSession[str] = PromptSession()
    return await session.prompt_async(message, is_password=hidden)


async def secret(variable: str) -> str:
    """A key typed without echo."""
    return (await _ask(f"  {variable}: ", hidden=True)).strip()


async def email() -> str:
    """Who signs in to the console."""
    typer.echo("\n  Who signs in to the console?")
    return (await _ask("  email     ")).strip()


async def password() -> str:
    """Their password, typed twice without echo until the two agree."""
    while True:
        first = await _ask("  password  ", hidden=True)
        again = await _ask("  again     ", hidden=True)
        if first == again:
            return first
        typer.echo("  the two differ: once more")


async def livekit_key() -> str:
    """The API key of the operator's own LiveKit."""
    return (await _ask("            API key     ")).strip()


async def livekit_secret() -> str:
    """Its secret, typed without echo."""
    return (await _ask("            API secret  ", hidden=True)).strip()
