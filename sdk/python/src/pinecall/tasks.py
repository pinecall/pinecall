"""A task: one thing a tool needs from the caller before it can finish, asked for mid-tool."""

import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from pinecall.errors import DeclarationRefused
from pinecall.wire.parts import ToolSpec

_T_co = TypeVar("_T_co", covariant=True)

A_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
GIVE = "give_"
AN_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
SHORTEST_NUMBER, LONGEST_NUMBER = 7, 15


@dataclass(frozen=True)
class Task(Generic[_T_co]):
    """What one task is: what it asks for, how, what the model gives, and what the tool is handed.

    Made with `task(...)`; a tool asks for it with `self.ask(GetEmail)`.
    """

    name: str
    asks: str
    fields: Mapping[str, str]
    check: Callable[[dict[str, str]], _T_co | Awaitable[_T_co]]
    how: str | None = None


_T = TypeVar("_T")


def task(
    name: str,
    *,
    asks: str,
    fields: Mapping[str, str],
    check: Callable[[dict[str, str]], _T | Awaitable[_T]],
    how: str | None = None,
) -> Task[_T]:
    """A task of your own.

    ```python
    Plate = task("plate", asks="the car's plate", fields={"plate": "As written."},
                 check=lambda given: given["plate"].upper())
    ```

    Args:
        name: names the tool the model gives it with: `email` is given with `give_email`.
        asks: what is asked for, as the model reads it: `"the caller's email address"`.
        fields: what the model gives, each with what it is; every one is a string.
        check: what the tool is handed, out of what the model gave; one that raises tells the
            model why, and it asks again.
        how: how to ask for it: `"Spell it back and wait for a yes."`.
    """
    if not A_NAME.match(name):
        raise DeclarationRefused(
            "a task's name is lowercase letters, digits and underscores:"
            " it names the tool the model gives it with"
        )
    if not asks.strip():
        raise DeclarationRefused(
            f'the task {name} says what it asks for: asks="the caller\'s email address"'
        )
    if not fields:
        raise DeclarationRefused(
            f'the task {name} names what the model gives: fields={{"email": "the address"}}'
        )
    if not callable(check):
        raise DeclarationRefused(
            f"the task {name} has a check: what the tool is handed, out of what the model gave"
        )
    return Task(name, asks, dict(fields), check, how)


def tasks_of(cls: type) -> list[Task[object]]:
    """The tasks a class declares: `tasks = [GetEmail, GetPhone]`."""
    declared: object = getattr(cls, "tasks", ())
    if not isinstance(declared, Sequence) or not all(
        isinstance(one, Task)
        for one in declared  # pyright: ignore[reportUnknownVariableType]
    ):
        raise DeclarationRefused(
            f"{cls.__name__}: tasks is a list of tasks, like [GetEmail, GetPhone]"
        )
    return list(declared)  # pyright: ignore[reportUnknownArgumentType]


def given_with(asked: Task[object]) -> str:
    """The name of the tool a task is given with."""
    return f"{GIVE}{asked.name}"


def giving_tool(asked: Task[object]) -> ToolSpec:
    """The tool a task is given with, as it is declared."""
    return ToolSpec(
        name=given_with(asked),
        description=(
            f"Give {asked.asks}, once the caller gave it to you."
            " Never guess it and never make one up."
        ),
        parameters={
            "type": "object",
            "properties": {
                name: {"type": "string", "description": what} for name, what in asked.fields.items()
            },
            "required": list(asked.fields),
        },
    )


def asking_for(asked: Task[object]) -> str:
    """What the model is told when a tool stops to ask."""
    how = "" if asked.how is None else f" {asked.how}"
    return (
        f"This is not done yet: it needs {asked.asks}. Ask the caller for it now.{how}"
        f" Then call {given_with(asked)}."
    )


def _email(given: dict[str, str]) -> str:
    address = given["email"].strip().lower()
    if not AN_EMAIL.match(address):
        raise ValueError(
            f'"{given["email"]}" is not an email address. Ask them to say it again, slowly.'
        )
    return address


def _phone(given: dict[str, str]) -> str:
    number = given["number"]
    digits = re.sub(r"\D", "", number)
    if not SHORTEST_NUMBER <= len(digits) <= LONGEST_NUMBER:
        raise ValueError(f'"{number}" is not a phone number. Ask for it again, digit by digit.')
    return f"+{digits}" if number.strip().startswith("+") else digits


def _name(given: dict[str, str]) -> dict[str, str]:
    first, last = given["first"].strip(), given["last"].strip()
    if not first or not last:
        raise ValueError("Both names are needed. Ask for the one that is missing.")
    return {"first": first, "last": last}


GetEmail: Task[str] = task(
    "email",
    asks="the caller's email address",
    how="Spell it back to them letter by letter and wait for a yes.",
    fields={
        "email": "The address as it is typed, like ana@example.com:"
        " no spaces, no words like 'at' or 'dot'."
    },
    check=_email,
)
"""The caller's email address, lowercased."""

GetPhone: Task[str] = task(
    "phone",
    asks="a phone number to reach the caller at",
    how="Read it back in groups of digits and wait for a yes.",
    fields={
        "number": "The number in digits, with its country code when they said one: +14155550142."
    },
    check=_phone,
)
"""The caller's phone number, digits only, with its `+` when they gave a country code."""

GetName: Task[dict[str, str]] = task(
    "name",
    asks="the caller's first and last name",
    how="Ask how the last name is spelled when it is not a common one.",
    fields={"first": "Their first name.", "last": "Their last name."},
    check=_name,
)
"""The caller's first and last name."""
