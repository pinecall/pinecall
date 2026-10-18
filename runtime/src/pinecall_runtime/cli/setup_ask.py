"""What `setup` asks at a terminal: the machine, the stack that fits it, a stage changed with completion, the keys."""

import os
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path

import typer
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter

from pinecall_runtime.cli.setup_models import (
    LOCAL,
    LOCAL_STT,
    TURNS,
    Choices,
    check_choices,
    is_local,
    local_or_vendor,
    model_of,
    turn_of,
    vendor_of,
)
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.providers import service as providers

# What a stage is called on the screen, and the field it is.
STAGE_WORDS: dict[str, str] = {
    "ears": "stt",
    "turn": "turn",
    "thinking": "llm",
    "voice": "tts",
    "judge": "judge",
    "caller": "caller",
}
# The stage a field is checked against, for the vendors that do it.
STAGE_OF = {"stt": "stt", "llm": "llm", "tts": "tts", "judge": "llm", "caller": "llm"}
FOLLOWS = "the thinking's model"
TURN_WORDS = {
    "stt": "the ears' own endpointing",
    "smart-turn": "Smart Turn v3, on the worker's CPU",
    "livekit": "livekit's v1-mini, on the worker's CPU",
}
NOWHERE = "not found: asked when you press Enter"
ONE_GIB = "{gib:.1f} GB"


def chosen(machine: providers.Machine, fits: providers.Recommendation, base: Choices) -> Choices:
    """The screen: the machine and the stack; Enter runs it, a stage's word changes that stage; the choices checked."""
    typer.echo(panel(machine, fits))
    current = base
    while True:
        typer.echo(stack(current, fits))
        word = _line("  Enter runs it, or a stage to change: ", list(STAGE_WORDS)).lower()
        if word == "":
            try:
                return check_choices(current)
            except ValidationError as refused:
                typer.echo(f"  {refused}")
                continue
        field = STAGE_WORDS.get(word)
        if field is None:
            typer.echo(f"  {word!r} is no stage: {' · '.join(STAGE_WORDS)}")
            continue
        current = changed(current, field, machine, fits)


def panel(machine: providers.Machine, fits: providers.Recommendation) -> str:
    """This machine in a few lines: what it computes on, Docker and Ollama, each measured model and whether it fits."""
    lines = ["", "  this machine", f"    {_computes_on(machine, fits)}"]
    held = f" ({', '.join(machine.ollama_models)})" if machine.ollama_models else ""
    lines.append(
        f"    Docker {'✓' if machine.docker else '✗ (needed)'} · Ollama {'✓' + held if machine.ollama_here else '✗'}"
    )
    lines.append("")
    lines.append("  measured models")
    for one in fits.candidates:
        room = "fits" if one.fits else f"short by {ONE_GIB.format(gib=one.short_by_gib)}"
        needs = ONE_GIB.format(gib=one.needs_gib)
        lines.append(
            f"    {one.model:<34} {needs:>8}   {room:<18} {one.first_token_s:.2f} s to first token · {one.did}"
        )
    for note in fits.notes:
        lines.append(f"  {note}")
    return "\n".join(lines)


def stack(
    choices: Choices,
    fits: providers.Recommendation,
    environ: Mapping[str, str] = os.environ,
    home: Path | None = None,
) -> str:
    """The stack, a line per stage: the choice, and beside it what runs it and where its key is."""
    lines = ["", "  the stack that fits it"]
    for word, field in STAGE_WORDS.items():
        said = getattr(choices, field)
        shown = said if said is not None else FOLLOWS
        lines.append(f"    {word:<9} {shown:<40} {_beside(field, said, choices, fits, environ, home)}")
    return "\n".join(lines)


def changed(choices: Choices, field: str, machine: providers.Machine, fits: providers.Recommendation) -> Choices:
    """One stage asked again, with completion over everything that could run it; the choices with that stage."""
    if field == "turn":
        turns = [
            turn for turn in TURNS if turn != "stt" or (not is_local(choices.stt) and providers.ends_turns(choices.stt))
        ]
        return replace(choices, turn=turn_of(_line("  turn: ", turns, choices.turn)))
    current = getattr(choices, field) or choices.llm
    picked = local_or_vendor(_line(f"  {_word_of(field)}: ", words_for(field, machine, fits), current))
    if field == "stt":
        return replace(choices, stt=picked)
    if field == "llm":
        return replace(choices, llm=picked)
    if field == "tts":
        return replace(choices, tts=picked)
    follows = None if picked == choices.llm else picked
    return replace(choices, judge=follows) if field == "judge" else replace(choices, caller=follows)


def words_for(field: str, machine: providers.Machine, fits: providers.Recommendation) -> list[str]:
    """What completes a stage: `local`, the local models (Ollama's own, the measured), the vendors that do it."""
    stage = STAGE_OF[field]
    words: list[str] = [LOCAL]
    if stage == "stt":
        words.append(f"{LOCAL}/{LOCAL_STT}")
    if stage == "llm":
        words.extend(f"{LOCAL}/{model}" for model in machine.ollama_models)
        words.extend(f"{LOCAL}/{one.model}" for one in fits.candidates)
    words.extend(
        sorted(name for name, vendor in providers.installed().items() if vendor.broken is None and stage in vendor.does)
    )
    return list(dict.fromkeys(words))


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


def _line(message: str, words: Iterable[str], default: str = "") -> str:
    typed: str = prompt(
        message, default=default, completer=WordCompleter(list(words), sentence=True), complete_while_typing=True
    )
    return typed.strip()


def _word_of(field: str) -> str:
    return next(word for word, named in STAGE_WORDS.items() if named == field)


def _computes_on(machine: providers.Machine, fits: providers.Recommendation) -> str:
    if machine.cards:
        cards = " + ".join(f"{card.name} · {ONE_GIB.format(gib=card.memory_gib)}" for card in machine.cards)
        return f"{cards} — {ONE_GIB.format(gib=fits.room_gib)} for the models beside the voice"
    if machine.apple_silicon:
        unified, room = ONE_GIB.format(gib=machine.ram_gib), ONE_GIB.format(gib=fits.room_gib)
        return f"Apple silicon · {unified} unified — {room} for the models"
    return f"no GPU · {ONE_GIB.format(gib=machine.ram_gib)} RAM · {machine.cores} cores"


def _beside(
    field: str,
    said: str | None,
    choices: Choices,
    fits: providers.Recommendation,
    environ: Mapping[str, str],
    home: Path | None,
) -> str:
    if field == "turn":
        return TURN_WORDS[choices.turn]
    if said is None:
        return ""
    if is_local(said):
        if field == "stt":
            return f"Whisper ({model_of(said) or LOCAL_STT}), on this machine"
        if field == "tts":
            return "Kokoro, on this machine"
        measured = next((one for one in fits.candidates if one.model == model_of(said)), None)
        return f"Ollama, {measured.first_token_s:.2f} s to first token" if measured else "Ollama"
    vendor = vendor_of(said)
    if not providers.takes_a_key(vendor):
        return vendor
    variable = providers.key_variable(vendor)
    where = providers.where_is_key(variable, environ, home)
    return f"{variable} in {where}" if where else f"{variable} {NOWHERE}"
