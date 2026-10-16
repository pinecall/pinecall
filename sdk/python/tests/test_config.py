"""What a class says of itself: its slug, and the environment it declares over the settings."""

from typing import ClassVar

import pytest

from pinecall import Agent, DeclarationRefused, judge, knowledge, llm, stt, voice
from pinecall._config import declared_on_the_instance, environment_of, slug_of
from pinecall.bridge import config_of


@voice("cartesia", "a0e99841-438c-4a64-b679-ae501e7d6091", model="sonic-2")
@llm(
    "openai/gpt-5.4-mini", temperature=0.3, builds="responses.LLM", options={"use_websocket": True}
)
@stt("soniox/stt-rt-v3", end_of_turn="smart-turn")
@judge("openai/qwen3-32b", options={"base_url": "http://gpu:8000/v1"})
@knowledge(path="knowledge.md", text="# Clínica Norte")
class Fijada(Agent):
    """Recepción que fija su voz, su modelo, sus oídos, su idioma y cómo abre."""

    language = "es"
    greeting = "Clínica Norte, buenas."
    hangup = "the caller says goodbye"
    hears: ClassVar = ["Vidal", "Sanitas"]
    memory: ClassVar = {"remember": ["alergias"], "forget": ["pagos"]}
    record = False


def test_what_the_class_declares_of_its_environment_is_sent_in_the_wires_shape() -> None:
    sent = config_of(Fijada).model_dump(exclude_none=True)

    assert sent["voice"] == {
        "provider": "cartesia",
        "voice_id": "a0e99841-438c-4a64-b679-ae501e7d6091",
        "model": "sonic-2",
    }
    assert sent["llm"] == {
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "temperature": 0.3,
        "builds": "responses.LLM",
        "options": {"use_websocket": True},
    }
    assert sent["stt"] == {"provider": "soniox", "model": "stt-rt-v3", "end_of_turn": "smart-turn"}
    assert sent["judge"] == {
        "provider": "openai",
        "model": "qwen3-32b",
        "options": {"base_url": "http://gpu:8000/v1"},
    }
    assert sent["hangup"] == {"when": "the caller says goodbye"}
    assert sent["knowledge"] == {"path": "knowledge.md", "text": "# Clínica Norte"}
    assert (sent["language"], sent["greeting"], sent["hears"]) == (
        "es",
        {"say": "Clínica Norte, buenas."},
        ["Vidal", "Sanitas"],
    )
    assert sent["record"] is False


def test_a_class_that_declares_no_environment_sends_none_of_it() -> None:
    class Clinica(Agent):
        """Una clínica."""

    assert environment_of(Clinica) == {}


def test_the_instances_knowledge_still_searches_beside_a_declared_one() -> None:
    assert callable(Fijada().knowledge.search)


def test_a_model_id_keeps_every_slash_after_the_vendors() -> None:
    @llm("livekit/openai/gpt-5-mini")
    class PorInferencia(Agent):
        """Por inferencia."""

    assert environment_of(PorInferencia)["llm"] == {
        "provider": "livekit",
        "model": "openai/gpt-5-mini",
    }


def test_an_environment_field_annotated_as_state_is_refused_with_how_to_declare_it() -> None:
    def declared() -> type[Agent]:
        class EnEspanol(Agent):
            """Una clínica."""

            language: str = "es"

        return EnEspanol

    with pytest.raises(DeclarationRefused) as refused:
        declared()

    assert str(refused.value) == (
        "`language` is the class's, not a call's state: "
        "declare it as a class attribute, `language = …` or `language: ClassVar = …`"
    )
    assert "@voice(" in declared_on_the_instance("voice")


def test_knowledge_written_as_an_attribute_is_refused_for_the_decorator() -> None:
    with pytest.raises(DeclarationRefused) as refused:
        type("Clinica", (Agent,), {"__doc__": "Una clínica.", "knowledge": {"path": "k.md"}})

    assert '@knowledge(path="…", text="…")' in str(refused.value)


def test_a_model_declared_by_decorator_and_attribute_both_is_refused() -> None:
    class DosVeces(Agent):
        """Dos veces."""

        llm: ClassVar = {"provider": "anthropic", "model": "claude-haiku-5-5"}

    with pytest.raises(DeclarationRefused, match="DosVeces declares both @llm"):
        llm("openai/gpt-5.4-mini")(DosVeces)


def test_the_slug_is_the_class_name_in_kebab_case_unless_the_class_names_one() -> None:
    class ClinicaNorte(Agent):
        """Una clínica."""

    class HTTPDesk(Agent):
        """Un mostrador."""

    class Named(Agent):
        """Con nombre."""

        slug = "recepcion"

    assert [slug_of(ClinicaNorte), slug_of(HTTPDesk), slug_of(Named)] == [
        "clinica-norte",
        "http-desk",
        "recepcion",
    ]
