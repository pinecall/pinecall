"""The outside events a class accepts, and from whom: its backend, or a browser in the call."""

import typing
from collections.abc import Mapping, Sequence

from pinecall.errors import DeclarationRefused
from pinecall.wire._names import EventSource
from pinecall.wire.parts import EventSpec

SOURCES: tuple[EventSource, ...] = typing.get_args(EventSource)


def accepted(
    cls: type, inherited: Mapping[str, tuple[EventSource, ...]]
) -> dict[str, tuple[EventSource, ...]]:
    """The events the class accepts, its parents' first; a name said again replaces the senders."""
    events = dict(inherited)
    said: object = vars(cls).get("accepts")
    if said is None:
        return events
    if not isinstance(said, Mapping):
        raise DeclarationRefused(
            f"{cls.__name__}.accepts names each event and who sends it:"
            ' {"slot.released": ["app"]}'
        )
    for name, senders in typing.cast("Mapping[object, object]", said).items():
        events[str(name)] = senders_of(cls, str(name), senders)
    return events


def senders_of(cls: type, name: str, senders: object) -> tuple[EventSource, ...]:
    """Who may send one event, refused when it names somebody who never sends any."""
    named = (senders,) if isinstance(senders, str) else senders
    if not isinstance(named, Sequence) or not named:
        raise DeclarationRefused(
            f"{cls.__name__}.accepts[{name!r}] names who sends it: app, participant, or both"
        )
    kept: list[EventSource] = []
    for sender in typing.cast("Sequence[object]", named):
        if sender not in SOURCES:
            raise DeclarationRefused(
                f"{cls.__name__}.accepts[{name!r}]: {sender!r} sends nothing;"
                " an event comes from app or participant"
            )
        kept.append(sender)
    return tuple(kept)


def specs_of(events: Mapping[str, tuple[EventSource, ...]]) -> list[EventSpec]:
    """The events as `agent.configure` carries them."""
    return [
        EventSpec.model_validate({"name": name, "from": list(senders)})
        for name, senders in events.items()
    ]


def takes(events: Mapping[str, tuple[EventSource, ...]], name: str, source: EventSource) -> bool:
    """Whether an event of this name, from this sender, reaches the class's `on_event`."""
    return source in events.get(name, ())
