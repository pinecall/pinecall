"""What `setup` asks at a terminal: a stage at a time, everything that could run it listed, a key as it is picked."""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import typer
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter

from pinecall_runtime.cli.setup_models import (
    KEYS_DEFAULTS,
    LOCAL,
    LOCAL_EMBEDDER,
    TURNS,
    Choices,
    Turn,
    check_choices,
    is_local,
    local_or_vendor,
    turn_of,
    vendor_of,
)
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.providers import service as providers

# The stages in the order they are asked: the field, the word on the screen, what it asks.
STAGES: tuple[tuple[str, str, str], ...] = (
    ("stt", "ears", "who hears the caller"),
    ("turn", "turn", "who ends the caller's turn"),
    ("llm", "thinking", "who thinks"),
    ("tts", "voice", "who speaks"),
    ("judge", "judge", "who judges a finished call"),
    ("caller", "caller", "who plays the simulated caller"),
)
# The stage a field's vendors are looked up by.
STAGE_OF = {"stt": "stt", "llm": "llm", "tts": "tts", "judge": "llm", "caller": "llm"}
RECOMMENDED = "recommended"
FOLLOWS = "the thinking's"
ASKED_NOW = "asked now if you pick it"
NO_KEY = "no key needed"
BY_NAME = "type a name, Tab completes"
TURN_WORDS: dict[Turn, str] = {
    "stt": "the ears' own endpointing",
    "smart-turn": "Smart Turn v3, on the worker's CPU",
    "livekit": "livekit's v1-mini, on the worker's CPU",
}
LOCAL_WORDS = {"stt": "Whisper large-v3 turbo, on this machine", "tts": "Kokoro, on this machine"}
ONE_GIB = "{gib:.1f} GB"
type Read = Callable[[str], str]


@dataclass(frozen=True)
class Option:
    """One thing that could run a stage: its choice as `setup` takes it, and what the screen says beside it."""

    choice: str
    said: str
    # The key variable a vendor needs and is missing: asked the moment the option is picked.
    missing: str | None = None


def chosen(
    machine: providers.Machine,
    fits: providers.Recommendation,
    base: Choices,
    *,
    environ: Mapping[str, str] = os.environ,
    home: Path | None = None,
    read: Read | None = None,
    hidden: Read | None = None,
) -> tuple[Choices, dict[str, str]]:
    """The stack asked a stage at a time; Enter takes the default. The choices, and the keys typed on the way."""
    ask_secret = hidden or secret
    typed: dict[str, str] = {}
    typer.echo(panel(machine, fits))
    while True:
        current = base
        for field, word, asks in STAGES:
            options = options_for(field, current, machine, fits, environ, home)
            follows = current.llm if field in ("judge", "caller") else None
            reader = read or _completing([one.choice for one in options])
            usual = KEYS_DEFAULTS.get(STAGE_OF.get(field, field))
            picked = _pick(word, asks, options, getattr(current, field), reader, usual=usual, follows=follows)
            if picked is None:
                continue
            if picked.missing is not None and picked.missing not in typed:
                typed[picked.missing] = ask_secret(picked.missing)
            elif not is_local(picked.choice) and field != "turn" and providers.takes_a_key(vendor_of(picked.choice)):
                variable = providers.key_variable(vendor_of(picked.choice))
                typer.echo(f"  {variable} read from {providers.where_is_key(variable, environ, home)}")
            current = _with(current, field, picked.choice)
        typer.echo(stack(current))
        (read or _line)("  Enter runs it: ")
        try:
            return check_choices(current), typed
        except ValidationError as refused:
            typer.echo(f"  {refused}")


def panel(machine: providers.Machine, fits: providers.Recommendation) -> str:
    """This machine in one line: what it computes on and what is left for the models, Docker, Ollama and its models."""
    held = f" ({', '.join(machine.ollama_models)})" if machine.ollama_models else ""
    ollama = f"Ollama ✓{held}" if machine.ollama_here else "Ollama ✗"
    docker = "Docker ✓" if machine.docker else "Docker ✗ (needed)"
    return f"\n  this machine   {_computes_on(machine, fits)} · {docker} · {ollama}"


def stack(choices: Choices) -> str:
    """The stack as chosen, on one line, before it runs."""
    runs = {
        "ears": choices.stt,
        "turn": choices.turn,
        "thinking": choices.llm,
        "voice": choices.tts,
        "judge": choices.judging,
        "caller": choices.calling,
    }
    return "\n  the stack\n    " + " · ".join(f"{word} {choice}" for word, choice in runs.items())


def options_for(
    field: str,
    choices: Choices,
    machine: providers.Machine,
    fits: providers.Recommendation,
    environ: Mapping[str, str] = os.environ,
    home: Path | None = None,
) -> list[Option]:
    """Everything that could run a stage: the open models here first, then every installed vendor doing it."""
    if field == "turn":
        ears_end = not is_local(choices.stt) and providers.ends_turns(vendor_of(choices.stt))
        return [Option(turn, TURN_WORDS[turn]) for turn in TURNS if turn != "stt" or ears_end]
    stage = STAGE_OF[field]
    options: list[Option] = []
    if stage == "llm":
        for one in fits.candidates:
            room = (
                f"fits · {one.first_token_s:.2f} s to first token"
                if one.fits
                else f"short by {ONE_GIB.format(gib=one.short_by_gib)}"
            )
            options.append(Option(f"{LOCAL}/{one.model}", f"Ollama · {room}"))
        # The embedder is pulled beside the models and thinks nothing: never offered as one. Ollama
        # lists a tag pulled bare as `<name>:latest`.
        listed = {one.model for one in fits.candidates} | {LOCAL_EMBEDDER}
        options.extend(
            Option(f"{LOCAL}/{tag}", "Ollama · pulled already")
            for tag in machine.ollama_models
            if tag.removesuffix(":latest") not in listed
        )
    else:
        options.append(Option(LOCAL, LOCAL_WORDS[stage]))
    for name, vendor in sorted(providers.installed().items()):
        if vendor.broken is None and stage in vendor.does:
            options.append(_vendor_option(name, environ, home))
    return options


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


# ── private ──


# One stage on the screen, numbered, the default marked; Enter is the default, a number or a name
# picks. A judge or caller following the thinking is one line: Enter leaves it following (None),
# a name picks, anything else shows the list. The list is what can run with nothing more asked —
# the open models, a vendor whose key is found — then the default and the stage's usual vendor;
# every other vendor is one line, taken by its name.
def _pick(
    word: str,
    asks: str,
    options: list[Option],
    default: str | None,
    ask_line: Read,
    *,
    usual: str | None = None,
    follows: str | None = None,
) -> Option | None:
    if default is None and follows is not None:
        typer.echo("")
        answer = ask_line(f"  {word} — {asks}   [{FOLLOWS}: {follows}]: ").strip()
        if answer == "":
            return None
        found = _named(answer, options)
        if found is not None:
            return found
    listed = [one for one in options if one.choice in (default, usual) or (one.missing is None and one.said != NO_KEY)]
    more = [one.choice for one in options if one not in listed]
    typer.echo(f"\n  {word} — {asks}")
    default_n = next((n for n, one in enumerate(listed, 1) if one.choice == default), None)
    for n, one in enumerate(listed, 1):
        mark = f"   {RECOMMENDED}" if n == default_n else ""
        typer.echo(f"    {n:<3}{one.choice:<40} {one.said}{mark}")
    if more:
        typer.echo(f"       … {len(more)} more: {', '.join(more[:3])} … — {BY_NAME}")
    shown = str(default_n) if default_n is not None else FOLLOWS
    while True:
        answer = ask_line(f"  {word} [{shown}]: ").strip()
        if answer == "":
            return listed[default_n - 1] if default_n is not None else None
        if answer.isdigit() and 1 <= int(answer) <= len(listed):
            return listed[int(answer) - 1]
        found = _named(answer, options)
        if found is not None:
            return found
        typer.echo(f"  {answer!r} is none of them: a number from 1 to {len(listed)}, or a name")


def _named(answer: str, options: list[Option]) -> Option | None:
    named = local_or_vendor(answer)
    return next((one for one in options if one.choice == named), None)


def _with(choices: Choices, field: str, picked: str) -> Choices:
    if field == "turn":
        return replace(choices, turn=turn_of(picked))
    if field == "stt":
        return replace(choices, stt=picked)
    if field == "llm":
        return replace(choices, llm=picked)
    if field == "tts":
        return replace(choices, tts=picked)
    follows = None if picked == choices.llm else picked
    return replace(choices, judge=follows) if field == "judge" else replace(choices, caller=follows)


def _vendor_option(name: str, environ: Mapping[str, str], home: Path | None) -> Option:
    if not providers.takes_a_key(name):
        return Option(name, NO_KEY)
    variable = providers.key_variable(name)
    where = providers.where_is_key(variable, environ, home)
    if where is not None:
        return Option(name, f"{variable} in {where}")
    return Option(name, f"{variable} — {ASKED_NOW}", missing=variable)


def _line(message: str) -> str:
    typed: str = prompt(message)
    return typed.strip()


# A stage's answer, completed over every choice it has as it is typed.
def _completing(words: list[str]) -> Read:
    completer = WordCompleter(words, sentence=True)

    def read(message: str) -> str:
        typed: str = prompt(message, completer=completer, complete_while_typing=True)
        return typed.strip()

    return read


def _computes_on(machine: providers.Machine, fits: providers.Recommendation) -> str:
    if machine.cards:
        cards = " + ".join(f"{card.name} · {ONE_GIB.format(gib=card.memory_gib)}" for card in machine.cards)
        return f"{cards} — {ONE_GIB.format(gib=fits.room_gib)} for the models beside the voice"
    if machine.apple_silicon:
        unified, room = ONE_GIB.format(gib=machine.ram_gib), ONE_GIB.format(gib=fits.room_gib)
        return f"Apple silicon · {unified} unified — {room} for the models"
    return f"no GPU · {ONE_GIB.format(gib=machine.ram_gib)} RAM · {machine.cores} cores"
