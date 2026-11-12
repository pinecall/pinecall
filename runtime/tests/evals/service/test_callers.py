"""Tests for the simulated caller: a model playing a persona, one line at a time."""

from dataclasses import replace

import pytest
from livekit.agents.llm import ChatMessage

from runtime.evals.service.callers import (
    Heard,
    Improvised,
    Spending,
    improvise_line,
    list_heard,
    pick_caller_voice,
)
from runtime.exceptions import UpstreamError
from runtime.judging import service as judging
from runtime.providers.catalog import Catalog
from runtime.wire.metrics import TTSModelUsage
from tests.conftest import configured
from tests.fakes.acme import ACME, VOICE, AcmeLLM
from tests.judging.factories import Scripted, a_log, agent, caller, entry

APURADO = judging.Persona(
    name="apurado",
    goal="cambiar la cita al martes por la tarde",
    style="frases cortas, interrumpe",
    facts={"name": "Ana García", "phone": "+34 600 000 001"},
)


def playing(line: str, *, hanging_up: bool = False) -> Scripted:
    """A caller model that says one line."""
    next_line: dict[str, object] = {
        "name": "say_next_line",
        "arguments": {"line": line, "hanging_up": hanging_up},
    }
    return Scripted(AcmeLLM(api_key="k", replies=[[next_line]]))


async def next_line(
    model: Scripted, persona: judging.Persona = APURADO, heard: tuple[Heard, ...] = (), turns_left: int = 3
) -> Improvised:
    """The caller's next line as the model improvises it, on a call that has three turns left."""
    return await improvise_line(model, persona, heard, turns_left)


def system_of(model: Scripted) -> str:
    return "\n".join(
        item.text_content or ""
        for item in model.requests[0].items
        if isinstance(item, ChatMessage) and item.role == "system"
    )


async def test_the_line_the_model_said_comes_back_with_its_hangup() -> None:
    model = playing("el martes por la tarde, la de las cuatro", hanging_up=True)
    line = await next_line(model)
    assert (line.say, line.hangup) == ("el martes por la tarde, la de las cuatro", True)


async def test_the_persona_and_its_facts_are_what_the_model_is_told_it_is() -> None:
    model = playing("hola")
    await next_line(model)
    system = system_of(model)
    assert "cambiar la cita al martes por la tarde" in system
    assert "frases cortas, interrumpe" in system
    assert "Ana García" in system
    assert "+34 600 000 001" in system


async def test_a_persona_with_no_facts_is_told_to_make_none_up() -> None:
    model = playing("hola")
    await next_line(model, replace(APURADO, facts={}))
    assert "do not make any up" in system_of(model)


async def test_the_call_so_far_arrives_with_the_business_as_the_one_talking_to_the_caller() -> None:
    model = playing("la de las cuatro")
    heard = (
        Heard("agent", "Clínica Norte, ¿en qué puedo ayudarle?"),
        Heard("caller", "quiero cambiar mi cita"),
        Heard("agent", "¿Para qué día?"),
    )
    await next_line(model, heard=heard, turns_left=2)
    history = [
        (item.role, item.text_content)
        for item in model.requests[0].items
        if isinstance(item, ChatMessage) and item.role != "system"
    ]
    assert history == [
        ("user", "Clínica Norte, ¿en qué puedo ayudarle?"),
        ("assistant", "quiero cambiar mi cita"),
        ("user", "¿Para qué día?"),
    ]


async def test_the_last_turn_is_announced_so_the_caller_says_goodbye_instead_of_being_cut() -> None:
    model = playing("gracias, hasta luego", hanging_up=True)
    await next_line(model, turns_left=1)
    assert "This is your last turn" in system_of(model)


async def test_a_caller_who_said_nothing_at_all_has_hung_up() -> None:
    line = await next_line(playing("   "))
    assert (line.say, line.hangup) == ("", True)


# The rule is the judge's: a caller that saw it would play to it.
async def test_the_callers_own_rule_is_never_told_to_the_model_playing_it() -> None:
    model = playing("hola")
    await next_line(model, replace(APURADO, expects=("SECRET: the agent should give the price.",)))
    assert "SECRET" not in str([item.text_content for item in model.requests[0].items if isinstance(item, ChatMessage)])


async def test_a_model_that_called_nothing_twice_is_a_vendor_failure_and_says_what_it_said() -> None:
    model = Scripted(AcmeLLM(api_key="k", replies=[["no pienso llamar a la herramienta"], ["tampoco ahora"]]))
    with pytest.raises(UpstreamError, match="say_next_line: it said 'tampoco ahora'"):
        await next_line(model)
    assert len(model.requests) == 2


# A local model (gemma4:12b on Ollama, 2026-10-17) now and then answers a caller's line in words:
# asked once more, as a judge is, it calls the tool.
async def test_a_model_that_answered_in_words_is_asked_once_more_and_its_line_said() -> None:
    said: dict[str, object] = {"name": "say_next_line", "arguments": {"line": "Mi pedido llegó roto."}}
    model = Scripted(AcmeLLM(api_key="k", replies=[["Hola, llamo por un pedido"], [said]]))
    improvised = await next_line(model)
    assert improvised.say == "Mi pedido llegó roto."
    assert len(model.requests) == 2


def test_both_sides_of_a_log_are_read_in_order_as_the_caller_heard_them() -> None:
    log = [*a_log(caller("hola"), agent("buenas")), entry(3, "tool.call", {})]
    assert [(spoken.who, spoken.said) for spoken in list_heard(log)] == [
        ("caller", "hola"),
        ("agent", "buenas"),
    ]


def priced(ceiling_usd: float | None) -> Catalog:
    """The box's row, its voice priced by the character, with the caller's ceiling when given."""
    row = configured().model_dump(mode="json")
    row["rates"]["acme-voice"] = {"characters": 0.001}
    if ceiling_usd is not None:
        row["caller"] = {"ceiling_usd": ceiling_usd}
    return Catalog.model_validate(row)


def spoken(line: Improvised) -> TTSModelUsage:
    """What the caller's voice used to say the line: its characters, on the box's voice."""
    return TTSModelUsage(provider=ACME, model=VOICE, characters_count=len(line.say))


async def test_a_callers_lines_and_voice_are_priced_and_it_stops_at_the_ceiling() -> None:
    spending = Spending(priced(0.02))
    line = await next_line(playing("diez letras"))
    assert not spending.is_over
    spending.count(line.usage)
    spending.count(spoken(line))
    # 20 tokens in at $1 and 5 out at $2 a million; 11 characters at $0.001.
    assert spending.usd == pytest.approx(0.00003 + 0.011)
    assert not spending.is_over
    spending.count(line.usage)
    spending.count(spoken(line))
    assert spending.is_over


async def test_a_row_with_no_caller_ceiling_never_stops_a_caller() -> None:
    spending = Spending(priced(None))
    line = await next_line(playing("una línea bastante larga " * 40))
    for _ in range(5):
        spending.count(line.usage)
        spending.count(spoken(line))
    assert spending.usd > 1
    assert not spending.is_over


# ── the voice the caller speaks in ──

VOICES = {"acme/es": "marcos", "acme/en": "henry", "acme/fr": "amelie", "other/es": "lucia"}


def test_the_caller_speaks_in_the_first_voice_of_its_language_when_the_agent_has_another() -> None:
    assert pick_caller_voice(VOICES, "acme", "someone-else", "es-ES") == "marcos"


def test_an_agent_that_speaks_in_that_voice_has_its_caller_in_another() -> None:
    assert pick_caller_voice(VOICES, "acme", "marcos", "es") == "henry"


def test_a_language_with_no_voice_of_its_own_is_called_in_englishs() -> None:
    assert pick_caller_voice(VOICES, "acme", None, "de") == "henry"


def test_no_caller_voice_is_the_one_the_agent_is_given() -> None:
    for agents_voice in VOICES.values():
        assert pick_caller_voice(VOICES, "acme", agents_voice, "es") != agents_voice


def test_a_persona_with_a_voice_of_its_own_speaks_in_it_unless_it_is_the_agents() -> None:
    assert pick_caller_voice(VOICES, "acme", "marcos", "es", "lucia") == "lucia"
    assert pick_caller_voice(VOICES, "acme", "marcos", "es", "marcos") != "marcos"


def test_a_vendor_the_operator_gave_no_voice_speaks_with_its_own() -> None:
    assert pick_caller_voice(VOICES, "nobody", None, "es") is None
