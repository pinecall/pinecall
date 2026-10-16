"""A judge and a persona as values: one question of a call; one caller a model plays."""

import re
from dataclasses import dataclass, field

from pinecall_runtime.enums import JudgeAnswer, JudgeRunsWhen
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.text import Json, JsonObject

# The name call.score gives the answer, and `--persona` takes: lower-case words joined by hyphens.
A_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Fewer than two is not a choice.
FEWEST_CHOICES = 2

NOT_A_JUDGE_NAME = "{name!r} is not a judge's name: lower-case words joined by hyphens, like offers-next-slot"
NO_QUESTION = "a judge asks a question of a call: write one"
NO_CHOICES = "a judge that answers one of several needs at least two choices"
NO_TRIGGER = "a judge that runs on a trigger needs the trigger's question"
CHOICES_ONLY = "only a judge that answers one of several takes choices"

# Each line is one demand a judge reads; past this a persona is a script, not a caller.
MOST_EXPECTS = 20
# A pause past this is a caller who left, not one who thinks.
LONGEST_PAUSE_S = 10.0
# Past this the agent hears noise, not a caller on a bad line.
MOST_PACKET_LOSS = 0.5
# What a line carries behind the caller, when it carries anything: a level names it.
AMBIENCES = ("television", "cafe", "office", "street")
# A voice slower than half or faster than double is a tape effect, not a caller.
SLOWEST = 0.5
FASTEST = 2.0

NOT_A_PERSONA_NAME = "{name!r} is not a persona's name: lower-case words joined by hyphens, like price-shopper"
NO_GOAL = "a persona wants something: write its goal, in the first person"
NO_STYLE = "a persona talks some way: write its style"
BLANK_EXPECT = "an expectation is one line the agent is held to, and this one is blank"
TOO_MANY_EXPECTS = "a persona expects at most {most} things of the agent"
NOT_A_SHARE = "interrupts is a share of the agent's answers, from 0 to 1, not {value}"
NOT_A_PAUSE = "pause_s is seconds of silence before each line, from 0 to {most}, not {value}"
NOT_A_LOSS = "packet_loss is a share of the caller's packets, from 0 to {most}, not {value}"
NOT_A_MURMUR_SHARE = "backchannels is a share of the agent's answers, from 0 to 1, not {value}"
NOT_A_SPEED = "speed is how fast the caller speaks, from {slowest} to {fastest}, not {value}"
NOT_AN_AMBIENCE = "ambience is what plays behind the caller, one of {allowed}, not {value!r}"


@dataclass(frozen=True, slots=True)
class JudgeSpec:
    """One judge: its name, its question, how it answers, when it runs and what it reads."""

    name: str
    question: str
    answer: JudgeAnswer = JudgeAnswer.verdict
    choices: tuple[str, ...] = ()
    on: JudgeRunsWhen = JudgeRunsWhen.always
    trigger: str = ""
    # The call and its tool calls are always read; these add the agent's prompt, the evidence the
    # call carried (knowledge, documents searched, facts recalled) and the facts about the call.
    reads_prompt: bool = False
    reads_evidence: bool = False
    reads_facts: bool = False

    def __post_init__(self) -> None:
        if not A_NAME.match(self.name):
            raise ValidationError(NOT_A_JUDGE_NAME.format(name=self.name))
        if not self.question.strip():
            raise ValidationError(NO_QUESTION)
        if self.answer is JudgeAnswer.choice and len(self.choices) < FEWEST_CHOICES:
            raise ValidationError(NO_CHOICES)
        if self.answer is not JudgeAnswer.choice and self.choices:
            raise ValidationError(CHOICES_ONLY)
        if self.on is JudgeRunsWhen.trigger and not self.trigger.strip():
            raise ValidationError(NO_TRIGGER)

    @property
    def reads(self) -> tuple[str, ...]:
        """What the judge reads beyond the call, by the names the wire and the store use."""
        named = (("prompt", self.reads_prompt), ("evidence", self.reads_evidence), ("facts", self.reads_facts))
        return tuple(name for name, read in named if read)


@dataclass(frozen=True, slots=True)
class Behavior:
    """How the caller acts on a spoken line, beside what it says."""

    # The share of the agent's answers the caller talks over once the agent has started.
    interrupts: float = 0.0
    # Seconds of silence before each line: a caller who thinks, or looks for a paper.
    pause_s: float = 0.0
    # A voice under the caller's, this many dB below it; None: a quiet room.
    interferer_db: float | None = None
    # The share of the caller's packets the line loses.
    packet_loss: float = 0.0
    # The share of the agent's answers the caller murmurs an "mm-hmm" into, keeping its turn.
    backchannels: float = 0.0
    # How fast the caller speaks, 1 being the voice as the vendor reads it.
    speed: float = 1.0
    # What plays behind the caller when `interferer_db` sets a level.
    ambience: str = "television"

    def __post_init__(self) -> None:
        if not 0.0 <= self.interrupts <= 1.0:
            raise ValidationError(NOT_A_SHARE.format(value=self.interrupts))
        if not 0.0 <= self.backchannels <= 1.0:
            raise ValidationError(NOT_A_MURMUR_SHARE.format(value=self.backchannels))
        if not SLOWEST <= self.speed <= FASTEST:
            raise ValidationError(NOT_A_SPEED.format(slowest=SLOWEST, fastest=FASTEST, value=self.speed))
        if self.ambience not in AMBIENCES:
            raise ValidationError(NOT_AN_AMBIENCE.format(allowed=", ".join(AMBIENCES), value=self.ambience))
        if not 0.0 <= self.pause_s <= LONGEST_PAUSE_S:
            raise ValidationError(NOT_A_PAUSE.format(most=LONGEST_PAUSE_S, value=self.pause_s))
        if not 0.0 <= self.packet_loss <= MOST_PACKET_LOSS:
            raise ValidationError(NOT_A_LOSS.format(most=MOST_PACKET_LOSS, value=self.packet_loss))


@dataclass(frozen=True, slots=True)
class Persona:
    """A caller an eval plays: who they are, what they want, how they talk, what they expect."""

    name: str
    goal: str
    style: str
    about: str = ""
    facts: dict[str, str] = field(default_factory=dict[str, str])
    state: JsonObject = field(default_factory=dict[str, Json])
    # The vendors the caller is played on; None is the runtime's.
    llm: str | None = None
    tts: str | None = None
    voice: str | None = None
    # What the caller expects of the agent, one verifiable demand a line ("The agent should…"):
    # the expected-outcome judge reads them, and the model playing the caller never does.
    expects: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    behavior: Behavior = field(default_factory=Behavior)

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ValidationError(NO_GOAL)
        if not self.style.strip():
            raise ValidationError(NO_STYLE)
        if len(self.expects) > MOST_EXPECTS:
            raise ValidationError(TOO_MANY_EXPECTS.format(most=MOST_EXPECTS))
        if any(not line.strip() for line in self.expects):
            raise ValidationError(BLANK_EXPECT)


def check_persona_name(name: str) -> None:
    """Refuse a persona's name that is not lower-case words joined by hyphens."""
    if not A_NAME.match(name):
        raise ValidationError(NOT_A_PERSONA_NAME.format(name=name))
