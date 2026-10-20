"""A call's usage priced by the row's rates: a voice by the character, or by the second where its vendor bills audio."""

from pinecall_runtime.providers.schemas import Catalog, Rate, Stage
from pinecall_runtime.providers.service.prices import cost_of
from pinecall_runtime.wire.metrics import TTSModelUsage

GEMINI = TTSModelUsage(provider="Gemini", model="gemini-3.8-flash-lite-tts", characters_count=600, audio_duration=32.0)
CARTESIA = TTSModelUsage(provider="Cartesia", model="sonic-3", characters_count=600, audio_duration=32.0)


def priced(rates: dict[str, Rate]) -> Catalog:
    return Catalog(defaults={"llm": Stage(vendor="acme")}, rates=rates)


def test_a_voice_whose_rate_is_per_second_of_audio_is_priced_by_the_audio_it_made() -> None:
    cost = cost_of([GEMINI], priced({"gemini-3.8-flash-lite-tts": Rate(audio_seconds=0.00015)}))
    assert [(row.unit, row.quantity, row.usd) for row in cost.rows] == [("audio_seconds", 32.0, 0.0048)]


def test_a_voice_whose_rate_is_per_character_is_priced_by_the_characters_it_read() -> None:
    cost = cost_of([CARTESIA], priced({"sonic-3": Rate(characters=0.00005)}))
    assert [(row.unit, row.quantity, row.usd) for row in cost.rows] == [("characters", 600, 0.03)]


def test_a_voice_with_no_rate_is_listed_unpriced_never_priced_at_zero() -> None:
    cost = cost_of([GEMINI], priced({}))
    assert (cost.rows, [(row.provider, row.model) for row in cost.unpriced]) == (
        [],
        [("Gemini", "gemini-3.8-flash-lite-tts")],
    )
