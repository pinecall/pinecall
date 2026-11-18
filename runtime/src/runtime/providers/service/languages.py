"""A call's languages against the row: what a stage its agent names nothing for runs, and what else would take them."""

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass

from runtime.enums import Stage
from runtime.exceptions import PinecallError
from runtime.providers.catalog import Catalog, StageChoice
from runtime.providers.service.keyring import Keyring, running_on
from runtime.providers.stage import Running


@dataclass(frozen=True, slots=True)
class Suited:
    """A model of the row's that takes a call's languages, and whether this org may run it."""

    vendor: str
    model: str | None
    # Why this org cannot run it, in the sentence a call would close with; None where it can.
    refused: str | None = None


# A call must run: ears its org has no key for are never chosen for it, however well they would hear.
# Until 2026-11-18 the first of the row's that heard the language was, whoever could run it, and an
# org lent nothing of that vendor had its call refused.
def choose_for(stage: Stage, languages: Sequence[str], catalog: Catalog, keys: Keyring) -> StageChoice:
    """What a stage its agent names nothing for runs: of the row's, on a key of the org's, the first that takes the
    call's languages, else its main one; the default where none does."""
    default, *others = catalog.choices_for(stage)
    runnable = [default, *(one for one in others if _refusal_of(stage, one, catalog, keys) is None)]
    for wanted in (tuple(languages), tuple(languages[:1])):
        found = next((one for one in runnable if catalog.takes(stage, one.vendor, one.model, wanted)), None)
        if found is not None:
            return found
    return default


def list_suited(stage: Stage, languages: Sequence[str], catalog: Catalog, keys: Keyring) -> list[Suited]:
    """The row's own for a stage that take every one of the languages, in its order, each with why it cannot run."""
    return [
        Suited(one.vendor, one.model, _refusal_of(stage, one, catalog, keys))
        for one in catalog.choices_for(stage)
        if catalog.takes(stage, one.vendor, one.model, languages)
    ]


# A model the row calls multilingual is told no one language on a call that has several: named one, it
# keeps to it. Any other is told the call's main language, and listens for the rest where it takes a list.
def tell_languages(stage: Stage, running: Running, languages: Sequence[str], catalog: Catalog) -> Running:
    """The stage told the call's languages: the one it runs in, and, for ears, the ones to listen for."""
    several = len(languages) > 1 and catalog.is_multilingual(stage, running.vendor, running.model)
    told = dataclasses.replace(running, language=None if several or not languages else languages[0])
    if stage is not Stage.stt:
        return told
    # Ears are told to listen for the languages they hear alone: Flux refuses a hint it does not know.
    # An agent that says its languages is listened to in those; the row's own are for one that says none.
    listened = languages or catalog.hints
    heard = tuple(one for one in listened if not catalog.lacks(stage, running.vendor, running.model, (one,)))
    return dataclasses.replace(told, hints=heard)


# ── private ──


def _refusal_of(stage: Stage, choice: StageChoice, catalog: Catalog, keys: Keyring) -> str | None:
    try:
        running_on(keys, choice.vendor, choice.model or catalog.model_for(stage, choice.vendor))
    except PinecallError as refused:
        return str(refused)
    return None
