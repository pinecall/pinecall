"""The voice picker's list: the voices the providers row lists for a vendor, else the ones its plugin lists."""

import dataclasses
import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.enums import Stage
from runtime.exceptions import NotFound, ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.text import a_list, a_mapping
from runtime.providers.catalog import Catalog
from runtime.providers.service import plugins
from runtime.providers.service.catalog import get_catalog
from runtime.providers.service.keyring import keys_of
from runtime.providers.service.pipeline import stage_on_its_key
from runtime.providers.service.refusals import refusing
from runtime.providers.service.signatures import lists_voices
from runtime.providers.service.stages import voice_outside_a_call
from runtime.providers.stage import Running, Voice, primary_language

NOT_LISTED = "it has no voice called {voice}: `pinecall voices list --tts {vendor}` lists the ones it has"
# Plugins name a voice's id and name differently; the first a row carries is it.
THE_ID = ("id", "voice_id", "voice")
THE_NAME = ("name", "voice_name", "display_name")
# A plugin that lists its voices with no language cannot be narrowed by one: every voice would pass
# the filter, and a person asking for Spanish would read 150 voices in every tongue. ElevenLabs'
# plugin lists 150 voices with no language, and `--language en` passed every one of them (2026-10-23).
NO_LANGUAGE_LISTED = (
    "{vendor} lists its voices with no language, so --language {language} cannot narrow them: drop it and pick by name"
)


class NotListed(NotFound):
    """The vendor lists no voices here."""

    def __init__(self, vendor: str) -> None:
        super().__init__(f"{vendor} lists no voices here: its voice is the vendor's own id, set as it is")


@dataclass(frozen=True, slots=True)
class ListedVoice:
    """A voice as the picker shows it: its id, its name, and the vendor's row whole."""

    id: str
    name: str
    detail: Mapping[str, Any]

    @property
    def language(self) -> str:
        """The language it speaks, where the listing says."""
        return str(self.detail.get("language") or "")

    @property
    def description(self) -> str:
        """What the vendor says of it."""
        return str(self.detail.get("description") or "")

    @property
    def gender(self) -> str:
        """Its gender, where the listing says."""
        return str(self.detail.get("gender") or "")

    @property
    def country(self) -> str:
        """Where its accent is from, where the listing says."""
        return str(self.detail.get("country") or "")

    @property
    def accent(self) -> str:
        """Its accent, where the listing says."""
        return str(self.detail.get("accent") or "")


@dataclass(frozen=True, slots=True)
class Listing:
    """What the picker was asked and what it shows: a vendor, a language, its voices in the vendor's order."""

    tts: str
    language: str | None
    voices: list[ListedVoice]


# Built as a call builds the stage: the operator's options, on the key a call would use.
async def list_for(session: AsyncSession, vault: Vault, scope: Scope, tts: str, language: str | None) -> Listing:
    """The voices the providers row lists for a vendor, else its plugin's; neither is a 404."""
    catalog = await get_catalog(session)
    named = plugins.parse_vendor(tts)
    spoken = primary_language(language)
    listed = list_in_catalog(catalog, named, spoken)
    # The row lists this vendor's voices by language: one it lists none in is said as that.
    if not listed and spoken is not None and list_in_catalog(catalog, named, None):
        raise NotFound(f"{named} lists no voice in {language}: drop --language to see every one")
    if not listed and not lists_voices(named, (Stage.tts,)):
        raise NotListed(named)
    if not listed:
        keys = await keys_of(session, vault, scope)
        running = stage_on_its_key(Stage.tts, Voice(vendor=named), catalog, keys)
        with refusing(named, "to list its voices"):
            listed = await list_by_vendor(dataclasses.replace(running, language=spoken))
        check_narrowable(named, listed, language)
    fits = [voice for voice in listed if spoken is None or not voice.language or voice.language.startswith(spoken)]
    return Listing(tts=tts, language=language, voices=fits)


# livekit's errors pass through: who asked says the vendor's no.
async def list_by_vendor(running: Running) -> list[ListedVoice]:
    """The voices a vendor lists on the stage's key, where its plugin lists any; NotFound if not."""
    async with voice_outside_a_call(running) as speech:
        listing = getattr(speech, "list_voices", None)
        if not callable(listing):
            raise NotListed(running.vendor)
        answer = listing()
        if not inspect.isawaitable(answer):
            raise NotListed(running.vendor)
        answered: object = await answer
    return [voice for row in _rows_of(answered) if (voice := _read_voice(row)) is not None]


# A vendor that speaks a voice it does not have in its default one (Google's Gemini voices) answers
# the trial, so the lists decide: one the providers row lists is kept; else the vendor's own list on
# the stage's key, cloned voices among them; a vendor that lists none (or an empty list) has the
# row's alone, and with none there either it is left to the trial. `agent set --voice zzz` was kept
# on Gemini (2026-10-25).
async def check_listed(running: Running, catalog: Catalog) -> None:
    """Refuse a voice neither the providers row nor the vendor lists; ValidationError naming the list."""
    if running.voice is None:
        return
    in_the_row = list_in_catalog(catalog, running.vendor, None)
    if _names(in_the_row, running.voice):
        return
    try:
        listed = await list_by_vendor(running)
    except NotListed:
        listed = []
    known = listed or in_the_row
    if known and not _names(known, running.voice):
        raise ValidationError(NOT_LISTED.format(vendor=running.vendor, voice=running.voice))


def list_in_catalog(catalog: Catalog, vendor: str, language: str | None) -> list[ListedVoice]:
    """The voices the providers row lists for a vendor, in that language or in every one."""
    return [
        ListedVoice(id=voice.id, name=voice.name, detail={**voice.model_dump(), "language": spoken})
        for spoken, voice in catalog.list_voices_for(vendor, language)
    ]


def check_narrowable(vendor: str, listed: Sequence[ListedVoice], language: str | None) -> None:
    """Refuse a language on a listing that carries none; nothing on a listing that does, or on no language."""
    if language is not None and listed and not any(item.detail.get("language") for item in listed):
        raise ValidationError(NO_LANGUAGE_LISTED.format(vendor=vendor, language=language))


def _names(listed: Sequence[ListedVoice], voice: str) -> bool:
    return any(voice in (each.id, each.name) for each in listed)


# A listing is a list of rows, each a dataclass or a mapping; one that is a mapping of names
# is read as rows named by its keys.
def _rows_of(answered: object) -> list[dict[str, Any]]:
    if a_mapping(answered):
        return [{"id": key, "name": key} for key in answered]
    return [_row_of(item) for item in answered] if a_list(answered) else []


def _row_of(item: object) -> dict[str, Any]:
    if dataclasses.is_dataclass(item) and not isinstance(item, type):
        return _as_json(dataclasses.asdict(item))
    return _as_json(item) if a_mapping(item) else {}


def _as_json(fields: Mapping[str, object]) -> dict[str, Any]:
    return {name: _plain(value) for name, value in fields.items()}


def _plain(value: object) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if a_mapping(value):
        return _as_json(value)
    if a_list(value):
        return [_plain(item) for item in value]
    return str(value)


def _read_voice(row: Mapping[str, Any]) -> ListedVoice | None:
    named = next((str(row[name]) for name in THE_ID if row.get(name)), None)
    if named is None:
        return None
    shown = next((str(row[name]) for name in THE_NAME if row.get(name)), named)
    return ListedVoice(id=named, name=shown, detail=row)
