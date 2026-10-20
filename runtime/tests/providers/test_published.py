"""What a vendor publishes, read from voicedex: the models a picker offers and the voices, with their previews."""

from collections.abc import Callable, Iterator
from datetime import date

import pytest
import voicedex
from voicedex.schema import Source

from pinecall_runtime.providers.service import published
from pinecall_runtime.providers.service.voices import ListedVoice

SOURCE = Source(url="https://example.com", read=date(2026, 10, 20))


def _model(id: str, *, selectable: bool = True, deprecated: bool = False) -> voicedex.ModelEntry:
    return voicedex.ModelEntry(
        id=id, name=id, stage="tts", vendor="acme", selectable=selectable, deprecated=deprecated, source=SOURCE
    )


def _voice(id: str, preview: str | None, **known: str) -> voicedex.VoiceEntry:
    return voicedex.VoiceEntry.model_validate(
        {"id": id, "name": id.title(), "vendor": "acme", "languages": ("es-AR",), "preview_url": preview, **known}
    )


def _models_answering(found: list[voicedex.ModelEntry]) -> Callable[..., list[voicedex.ModelEntry]]:
    def answer(**_: object) -> list[voicedex.ModelEntry]:
        return found

    return answer


def _voices_answering(found: list[voicedex.VoiceEntry]) -> Callable[..., list[voicedex.VoiceEntry]]:
    def answer(**_: object) -> list[voicedex.VoiceEntry]:
        return found

    return answer


@pytest.fixture(autouse=True)
def fresh() -> Iterator[None]:
    """Each test reads voicedex anew: the module keeps what it read for the life of the process."""
    published.models_of.cache_clear()
    published.voices_of.cache_clear()
    yield
    published.models_of.cache_clear()
    published.voices_of.cache_clear()


def test_a_picker_is_offered_only_current_ids_the_vendors_api_takes(monkeypatch: pytest.MonkeyPatch) -> None:
    listed = [_model("sonic-3"), _model("sonic-2", deprecated=True), _model("neural", selectable=False)]
    monkeypatch.setattr(voicedex, "models", _models_answering(listed))
    assert published.models_of("acme", "tts") == ("sonic-3",)


def test_a_published_voice_carries_its_preview_and_what_it_is(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        voicedex,
        "voices",
        _voices_answering([_voice("antonia", "https://x/antonia.wav", gender="female", accent="Argentine")]),
    )
    (antonia,) = published.voices_of("acme", "es-AR")
    assert antonia.detail == {
        "language": "es-AR",
        "description": "",
        "gender": "female",
        "accent": "Argentine",
        "preview_url": "https://x/antonia.wav",
    }


def test_a_listed_voice_is_given_what_voicedex_knows_and_keeps_what_it_says(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        voicedex, "voices", _voices_answering([_voice("ana", "https://x/ana.wav", gender="female", accent="Mexican")])
    )
    listed = [
        ListedVoice(id="ana", name="Ana", detail={"accent": "Rioplatense", "gender": ""}),
        ListedVoice(id="own-clone", name="Mine", detail={}),
    ]
    ana, mine = published.described("acme", listed)
    assert ana.detail["preview_url"] == "https://x/ana.wav"
    assert ana.detail["gender"] == "female"
    # The list's own word stands over voicedex's.
    assert ana.detail["accent"] == "Rioplatense"
    # A voice voicedex does not know (an org's own clone) is left as listed.
    assert mine == listed[1]


def test_a_vendor_voicedex_has_no_voice_of_lists_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voicedex, "voices", _voices_answering([]))
    assert published.lists_voices("acme") is False
