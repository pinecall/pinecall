"""What `setup` asks at a terminal: a key the runtime's defaults need and found nowhere, the console's person."""

import typer
from prompt_toolkit import prompt


def secret(variable: str) -> str:
    """A key typed without echo."""
    typed: str = prompt(f"  {variable}: ", is_password=True)
    return typed.strip()


def email() -> str:
    """Who signs in to the console."""
    typed: str = prompt("  console sign-in, your email: ")
    return typed.strip()


def password() -> str:
    """Their password, typed twice without echo until the two agree."""
    while True:
        first: str = prompt("  password: ", is_password=True)
        again: str = prompt("  again: ", is_password=True)
        if first == again:
            return first
        typer.echo("  the two differ: once more")
