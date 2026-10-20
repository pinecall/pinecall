"""What each vendor publishes of itself, from voicedex: the models a picker offers and the voices it plays."""

from functools import cache

import voicedex

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.providers.service.voices import ListedVoice


# voicedex's data is the release this build pins: it never changes while the process lives, so it is read once.
@cache
def models_of(vendor: str, stage: Modality) -> tuple[str, ...]:
    """The ids the vendor's API takes as a model for that stage, current ones only, in voicedex's order."""
    return tuple(
        model.id
        for model in voicedex.models(stage=stage, vendor_id=vendor)
        if model.selectable and not model.deprecated
    )


@cache
def voices_of(vendor: str, language: str | None) -> tuple[ListedVoice, ...]:
    """The voices the vendor publishes, in a language and its regions (`es` finds `es-AR`) or in every one."""
    return tuple(
        ListedVoice(
            id=voice.id,
            name=voice.name,
            detail={
                "language": voice.languages[0] if voice.languages else "",
                "description": voice.description,
                "gender": voice.gender or "",
                "accent": voice.accent or "",
                "preview_url": voice.preview_url,
            },
        )
        for voice in voicedex.voices(vendor_id=vendor, language=language)
    )


def lists_voices(vendor: str) -> bool:
    """Whether voicedex knows any voice of the vendor."""
    return bool(voices_of(vendor, None))


def described(vendor: str, listed: list[ListedVoice]) -> list[ListedVoice]:
    """Voices a vendor's plugin or the row listed, each given what voicedex knows of it that they lack: its
    preview, its gender, its accent. What they say themselves stands."""
    known = {voice.id: voice for voice in voices_of(vendor, None)}
    filled: list[ListedVoice] = []
    for item in listed:
        voice = known.get(item.id)
        own = {key: value for key, value in item.detail.items() if value}
        filled.append(
            item if voice is None else ListedVoice(id=item.id, name=item.name, detail={**voice.detail, **own})
        )
    return filled
