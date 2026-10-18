"""The words the ears are told to expect reach every plugin under the name it takes them, and the
language reaches one whose options are a single object: as an argument, or inside that object."""

from dataclasses import dataclass
from typing import Never, override

import pytest
from livekit.agents import stt

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.providers.service import stages
from pinecall_runtime.providers.service.plugins import Running

HEAR = ("Brisa", "Médano")


class _Ears(stt.STT[Never]):
    """Ears that keep what they were built with."""

    def __init__(self, **given: object) -> None:
        super().__init__(capabilities=stt.STTCapabilities(streaming=True, interim_results=True))
        self.given = given

    @override
    async def _recognize_impl(self, *args: object, **kwargs: object) -> stt.SpeechEvent:
        raise NotImplementedError


class TermsAsAnArgument(_Ears):
    """As Deepgram's and Cartesia's: `keyterm=[...]`."""

    def __init__(self, *, api_key: str, language: str | None = None, keyterm: list[str] | None = None) -> None:
        super().__init__(api_key=api_key, language=language, keyterm=keyterm)


@dataclass
class Context:
    terms: list[str] | None = None
    text: str | None = None


@dataclass
class Options:
    model: str = "rt"
    language_hints: list[str] | None = None
    context: Context | str | None = None


class TermsInsideItsOptions(_Ears):
    """As Soniox's: `params=STTOptions(language_hints=[...], context=ContextObject(terms=[...]))`."""

    def __init__(self, *, api_key: str, params: Options | None = None) -> None:
        super().__init__(api_key=api_key, params=params)


class NoTerms(_Ears):
    """Ears that take no words to expect: given none, never refused for it."""

    def __init__(self, *, api_key: str) -> None:
        super().__init__(api_key=api_key)


def _built(monkeypatch: pytest.MonkeyPatch, made: type, running: Running) -> dict[str, object]:
    def the_class(_modality: Modality, _running: Running) -> type:
        return made

    monkeypatch.setattr(stages, "_class_of", the_class)
    ears = stages.stt_of(running, None, HEAR)
    assert isinstance(ears, _Ears)
    return ears.given


def test_ears_that_take_an_argument_for_them_get_the_words_there(monkeypatch: pytest.MonkeyPatch) -> None:
    given = _built(monkeypatch, TermsAsAnArgument, Running(vendor="v", credentials="k", language="es"))
    assert given["keyterm"] == list(HEAR)
    assert given["language"] == "es"


def test_ears_that_take_one_options_object_get_the_words_and_the_language_inside_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    given = _built(monkeypatch, TermsInsideItsOptions, Running(vendor="v", credentials="k", language="es-UY"))
    assert given["params"] == Options(language_hints=["es"], context=Context(terms=list(HEAR)))


def test_what_the_row_put_in_the_options_object_stands(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"params": {"model": "rt-pro", "language_hints": ["pt"]}}
    given = _built(monkeypatch, TermsInsideItsOptions, Running(vendor="v", credentials="k", language="es", options=row))
    assert given["params"] == Options(model="rt-pro", language_hints=["pt"], context=Context(terms=list(HEAR)))


def test_ears_that_take_no_words_are_built_without_them(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _built(monkeypatch, NoTerms, Running(vendor="v", credentials="k")) == {"api_key": "k"}
