"""What a class says of itself: its slug, and the environment it declares over the settings."""

import re
from collections.abc import Callable, Mapping
from typing import TypeVar

from pinecall._opening import greeting_of, hangup_of
from pinecall._state import is_class_var, own_annotations
from pinecall.errors import DeclarationRefused
from pinecall.wire.parts import EndOfTurn

# The settings a class may declare; whatever it declares wins over the agent's settings. Word for
# word the TypeScript package's `ENVIRONMENT` and the gem's `Config::ENVIRONMENT`.
ENVIRONMENT: tuple[str, ...] = (
    "language",
    "voice",
    "llm",
    "stt",
    "judge",
    "greeting",
    "hangup",
    "turn",
    "says",
    "hears",
    "knowledge",
    "docs",
    "memory",
    "record",
)

# The ones a decorator declares: the models, the voice, and `knowledge`, which as an attribute
# would hide the instance's `self.knowledge.search`.
DECORATED: Mapping[str, str] = {
    "voice": '@voice("<vendor>", "<voice id>")',
    "llm": '@llm("<vendor>/<model>")',
    "stt": '@stt("<vendor>/<model>")',
    "judge": '@judge("<vendor>/<model>")',
    "knowledge": '@knowledge(path="…", text="…")',
}

# Where `@knowledge` keeps what it declares, beside the class's other attributes.
KNOWLEDGE = "_pinecall_knowledge"

_Class = TypeVar("_Class", bound=type)


def declared_on_the_instance(field: str) -> str:
    """The sentence a class that declares an environment field as state is refused with."""
    way = DECORATED.get(field, f"a class attribute, `{field} = …` or `{field}: ClassVar = …`")
    return f"`{field}` is the class's, not a call's state: declare it as {way}"


def refuse_the_environment(cls: type) -> None:
    """Refuse an environment field annotated as state, or written where a decorator declares it."""
    annotated = {name for name, said in own_annotations(cls).items() if not is_class_var(said)}
    written = set(vars(cls))
    for field in ENVIRONMENT:
        if field in annotated or (field == "knowledge" and field in written):
            raise DeclarationRefused(declared_on_the_instance(field))


def environment_of(cls: type) -> dict[str, object]:
    """The environment the class declares, as the declaration sends it."""
    declared: dict[str, object] = {}
    for field in ENVIRONMENT:
        value: object = getattr(cls, KNOWLEDGE if field == "knowledge" else field, None)
        if value is not None:
            declared[field] = value
    if "greeting" in declared:
        declared["greeting"] = greeting_of(declared["greeting"])
    if "hangup" in declared:
        declared["hangup"] = hangup_of(declared["hangup"])
    return declared


def voice(
    provider: str,
    voice_id: str,
    *,
    model: str | None = None,
    builds: str | None = None,
    options: Mapping[str, object] | None = None,
) -> Callable[[_Class], _Class]:
    """The voice, by its vendor and the vendor's own id for it; it wins over the agent's settings.

    Args:
        provider: The vendor that speaks, as `pinecall providers` names it.
        voice_id: The vendor's own id for the voice.
        model: The vendor's model, when its default is not wanted.
        builds: A class of the vendor's LiveKit plugin other than its TTS.
        options: That class's keyword arguments, as the plugin names them. With `builds`, they run
            only on the org's own key for the vendor.
    """
    given = {"model": model, "builds": builds, "options": options}
    return _declaring("voice", {"provider": provider, "voice_id": voice_id, **_set(given)})


def llm(
    model: str,
    *,
    temperature: float | None = None,
    builds: str | None = None,
    options: Mapping[str, object] | None = None,
) -> Callable[[_Class], _Class]:
    """The model that answers, `vendor/model` or a vendor alone; it wins over the agent's settings.

    Args:
        model: `vendor/model`, or a vendor alone to run its default model.
        temperature: How freely the model picks its words, in its vendor's range.
        builds: A class of the vendor's LiveKit plugin other than its LLM: `"responses.LLM"`.
        options: That class's keyword arguments, as the plugin names them (`use_websocket`).
            With `builds`, they run only on the org's own key for the vendor.
    """
    given = {"temperature": temperature, "builds": builds, "options": options}
    return _declaring("llm", {**_model_of(model), **_set(given)})


def stt(
    model: str,
    *,
    builds: str | None = None,
    options: Mapping[str, object] | None = None,
    end_of_turn: EndOfTurn | None = None,
) -> Callable[[_Class], _Class]:
    """The ears, `vendor/model` or a vendor alone; they win over the agent's settings.

    Args:
        model: `vendor/model`, or a vendor alone to run its default model.
        builds: A class of the vendor's LiveKit plugin other than its STT.
        options: That class's keyword arguments, as the plugin names them. With `builds`, they run
            only on the org's own key for the vendor.
        end_of_turn: Who says the caller's turn is over: `"stt"` the ears themselves (Deepgram
            Flux), `"livekit"` or `"smart-turn"` (Smart Turn v3), a model on the worker.
    """
    given = {"builds": builds, "options": options, "end_of_turn": end_of_turn}
    return _declaring("stt", {**_model_of(model), **_set(given)})


def judge(
    model: str,
    *,
    builds: str | None = None,
    options: Mapping[str, object] | None = None,
) -> Callable[[_Class], _Class]:
    """The model the agent's calls are judged on, over the org's choice and Pinecall's.

    On a key of the org's own for the vendor, a local model's server among them, its evals are
    never billed; on a key Pinecall lends they are. The judge is asked for a forced tool call, so
    the model must call tools.

    Args:
        model: `vendor/model`, or a vendor alone to run its default model.
        builds: A class of the vendor's LiveKit plugin other than its LLM.
        options: That class's keyword arguments, as the plugin names them
            (`{"base_url": "http://gpu:8000/v1"}` for a local server). With `builds`, they run
            only on the org's own key for the vendor.
    """
    given = {"builds": builds, "options": options}
    return _declaring("judge", {**_model_of(model), **_set(given)})


def knowledge(*, path: str, text: str) -> Callable[[_Class], _Class]:
    """Markdown read whole on every call; it wins over the agent's settings.

    Args:
        path: The file's name, as the console shows it.
        text: The Markdown itself.
    """
    return _declaring(KNOWLEDGE, {"path": path, "text": text})


def slug_of(cls: type) -> str:
    """The slug the class names itself with `slug = "…"`, else its name in kebab-case."""
    named = getattr(cls, "slug", None)
    if isinstance(named, str):
        return named
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", cls.__name__)
    return re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", spaced).lower()


# Both spellings on one class are refused, as `@render` and a `render` method are: one is dead.
def _declaring(field: str, value: Mapping[str, object]) -> Callable[[_Class], _Class]:
    def decorate(cls: _Class) -> _Class:
        if field in vars(cls):
            named = "knowledge" if field == KNOWLEDGE else field
            raise DeclarationRefused(
                f"{cls.__name__} declares both @{named}(…) and a {named} attribute; keep one"
            )
        setattr(cls, field, dict(value))
        return cls

    return decorate


# The model id keeps every slash after the vendor's: `livekit/openai/gpt-5-mini`.
def _model_of(named: str) -> dict[str, object]:
    provider, _, model = named.partition("/")
    return {"provider": provider, "model": model}


def _set(given: Mapping[str, object]) -> dict[str, object]:
    return {name: value for name, value in given.items() if value is not None}
