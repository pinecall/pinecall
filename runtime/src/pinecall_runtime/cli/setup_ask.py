"""What `setup` asks at a terminal: a key found nowhere, the console's person, the pair of a LiveKit of yours."""

import typer
from prompt_toolkit import prompt


def secret(variable: str) -> str:
    """A key typed without echo."""
    typed: str = prompt(f"  {variable}: ", is_password=True)
    return typed.strip()


def email() -> str:
    """Who signs in to the console."""
    typer.echo("\n  Who signs in to the console?")
    typed: str = prompt("  email     ")
    return typed.strip()


def password() -> str:
    """Their password, typed twice without echo until the two agree."""
    while True:
        first: str = prompt("  password  ", is_password=True)
        again: str = prompt("  again     ", is_password=True)
        if first == again:
            return first
        typer.echo("  the two differ: once more")


def livekit_key() -> str:
    """The API key of the operator's own LiveKit."""
    typed: str = prompt("            API key     ")
    return typed.strip()


def livekit_secret() -> str:
    """Its secret, typed without echo."""
    typed: str = prompt("            API secret  ", is_password=True)
    return typed.strip()
