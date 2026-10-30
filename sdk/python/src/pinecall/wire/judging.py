"""The judges and the personas a class declares: what `AgentConfig.judges` and `.personas` carry."""

from typing import Literal, TypeAlias

from pydantic import Field

from pinecall.wire._names import Json, JsonObject
from pinecall.wire.frames import WireModel

# How a judge answers, when it runs, what it reads beyond the call, and what plays behind a caller.
JudgeAnswer: TypeAlias = Literal["verdict", "choice", "score"]
JudgeRunsWhen: TypeAlias = Literal["always", "simulations", "trigger"]
JudgeRead: TypeAlias = Literal["prompt", "evidence", "facts"]
Ambience: TypeAlias = Literal["television", "cafe", "office", "street"]


class JudgeDeclaration(WireModel):
    """One judge of the agent's own, as its class declares it: `judges/<name>.md` read."""

    name: str
    question: str
    answer: JudgeAnswer = "verdict"
    # The answers a `choice` judge picks from: two at least, and only for `choice`.
    choices: list[str] = Field(default_factory=list[str])
    when: JudgeRunsWhen = "always"
    trigger: str = ""
    reads: list[JudgeRead] = Field(default_factory=list[JudgeRead])


class JudgesDeclared(WireModel):
    """The judges the class owns: which of Pinecall's its calls meet, and its own."""

    on: list[str] = Field(default_factory=list[str])
    own: list[JudgeDeclaration] = Field(default_factory=list[JudgeDeclaration])


class CallerBehavior(WireModel):
    """How a simulated caller acts on a spoken line, beside what it says."""

    interrupts: float = Field(default=0.0, ge=0.0, le=1.0)
    pause_s: float = Field(default=0.0, ge=0.0, le=10.0)
    interferer_db: float | None = None
    packet_loss: float = Field(default=0.0, ge=0.0, le=0.5)
    backchannels: float = Field(default=0.0, ge=0.0, le=1.0)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    ambience: Ambience = "television"


class PersonaDeclaration(WireModel):
    """One caller of the agent's own, as its class declares it: `test/personas/<name>.json` read."""

    name: str
    goal: str
    style: str
    about: str = ""
    facts: dict[str, str] = Field(default_factory=dict[str, str])
    state: JsonObject = Field(default_factory=dict[str, Json])
    expects: list[str] = Field(default_factory=list[str])
    tags: list[str] = Field(default_factory=list[str])
    behavior: CallerBehavior = Field(default_factory=CallerBehavior)
    llm: str | None = None
    tts: str | None = None
    voice: str | None = None


class PersonasDeclared(WireModel):
    """The personas the class owns: which of Pinecall's its runs play, and its own."""

    on: list[str] = Field(default_factory=list[str])
    own: list[PersonaDeclaration] = Field(default_factory=list[PersonaDeclaration])
