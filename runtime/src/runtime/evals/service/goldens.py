"""What a golden holds a call to: the checks its final expect sets, settled by code or asked of a judge."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from runtime.evals.service.matrix import Ruling, failing, passing, score_of
from runtime.judging import service as judging
from runtime.providers import service as providers
from runtime.wire.goldens import Golden, Register
from runtime.wire.runs import JudgeScore

TOOLS = "Every tool this golden names was called in the conversation."
NOT_TOOLS = "The conversation called none of the tools this golden forbids."
SAYS = "The agent said every phrase this golden names."
SAYS_ANY = "The agent said at least one of the phrases this golden accepts."
SILENCE = "The agent said none of the phrases this golden names."
REGISTER = "The agent addressed the caller as {register} in every one of its turns."
ON_THE_PANEL = "The judge {name} held of this call."
# A check that could not look must not pass: a judge nobody wrote breaks the golden.
NOT_ON_THE_PANEL = "this golden asks {name}, and there is no such judge: there are {panel}"
NEEDS_THE_MODEL = "{name} needs the judge model, and none was given"

# Unmistakable tú; `té` (tea) carries its accent, so `te` never matches it.
TUTEO: frozenset[str] = frozenset({"tú", "ti", "te", "contigo", "tu", "tus", "tuyo", "tuya", "tuyos", "tuyas"})
# `le`, `les`, `su` and `sus` are left out: they are as often the third person.
USTEO: frozenset[str] = frozenset({"usted", "ustedes", "consigo", "suyo", "suya", "suyos", "suyas"})
# The marks around a word, markdown's among them.
PUNCTUATION = ".,;:¿?¡!()\"'*_`~[]"


# Until 2026-11 each check was a subclass of livekit's `Judge`, built to be handed back to livekit's
# evaluation for a verdict the code had already reached.
@dataclass(frozen=True, slots=True)
class Settled:
    """A golden's expectation settled by code from the call."""

    name: str
    criteria: str
    ruling: Ruling


@dataclass(frozen=True, slots=True)
class Asked:
    """A judge of the agent's roster a golden names, asked of the golden's call."""

    judge: judging.RosterJudge

    @property
    def name(self) -> str:
        """The judge's name, which the golden asks it by."""
        return self.judge.spec.name


type Check = Settled | Asked


# `roster` is every judge the agent's calls may meet, the library's and the org's own, by name, on or
# off: a golden asks a judge by naming it.
def list_checks(
    golden: Golden, transcript: judging.Transcript, roster: Mapping[str, judging.RosterJudge]
) -> list[Check]:
    """One check per field of the final expect, then the judges it names, from the roster."""
    expect = golden.expect
    checks: list[Check] = []
    if expect.tools:
        checks.append(_check_tools(transcript, expect.tools))
    if expect.not_tools:
        checks.append(_check_not_tools(transcript, expect.not_tools))
    if expect.not_said:
        checks.append(_check_silence(transcript, expect.not_said))
    if expect.says:
        checks.append(_check_says(transcript, expect.says))
    if expect.says_any:
        checks.append(_check_says_any(transcript, expect.says_any))
    if expect.grounded:
        checks.append(_find_on_the_panel(roster, "grounded"))
    if expect.addressed_as is not None:
        checks.append(_check_register(transcript, expect.addressed_as))
    present = {check.name for check in checks}
    checks.extend(_find_on_the_panel(roster, name) for name in expect.judges if name not in present)
    return checks


# A judge the golden names is asked as the panel asks it: its gate first, then its question. Here its
# answer is a golden's: broken fails, anything else (held, a classification, N/A) holds.
async def score_golden(
    checks: Sequence[Check],
    transcript: judging.Transcript,
    context: judging.Context,
    model: providers.Answerer | None,
) -> list[JudgeScore]:
    """Every check over one call, in order: its ruling as a score, and the model's requests it made."""
    scores: list[JudgeScore] = []
    for check in checks:
        if isinstance(check, Settled):
            scores.append(score_of(check.name, check.criteria, check.ruling))
            continue
        question = check.judge.spec.question
        gate = judging.gate_of(check.judge, transcript)
        if gate is not None:
            scores.append(score_of(check.name, question, passing(gate)))
        elif model is None:
            scores.append(score_of(check.name, "", failing(NEEDS_THE_MODEL.format(name=check.name))))
        else:
            answered = await judging.ask_judge(check.judge, transcript, context, model)
            rule = failing if answered.verdict == "broken" else passing
            scores.append(score_of(check.name, question, rule(answered.reason), asked=len(answered.spent)))
    return scores


def _find_on_the_panel(roster: Mapping[str, judging.RosterJudge], name: str) -> Check:
    found = roster.get(name)
    if found is not None:
        return Asked(found)
    names = ", ".join(roster) or "no judge at all"
    return Settled(name, ON_THE_PANEL.format(name=name), failing(NOT_ON_THE_PANEL.format(name=name, panel=names)))


def _check_register(transcript: judging.Transcript, expected: Register) -> Settled:
    other = USTEO if expected == "tu" else TUTEO
    turns = transcript.lines_by(judging.AGENT)
    slips = [(number, word) for number, turn in enumerate(turns, 1) for word in _list_marks(turn, other)]
    if slips:
        spoken = "; ".join(f"{word!r} in agent turn {number}" for number, word in slips)
        ruling = failing(f"the agent was asked for {expected} and said {spoken}")
    else:
        ruling = passing(f"no word of the other register in {len(turns)} agent turn(s), asked for {expected}")
    return Settled("register", REGISTER.format(register=expected), ruling)


# The order the tools ran in is not judged.
def _check_tools(transcript: judging.Transcript, names: Sequence[str]) -> Settled:
    ran = {called.name for called in transcript.tool_calls}
    missing = [name for name in names if name not in ran]
    if missing:
        what_ran = ", ".join(sorted(ran)) or "no tool at all"
        ruling = failing(f"the golden expects {', '.join(missing)}, and this call ran {what_ran}")
    else:
        ruling = passing(f"every expected tool ran: {', '.join(names)}")
    return Settled("tools", TOOLS, ruling)


def _check_not_tools(transcript: judging.Transcript, names: Sequence[str]) -> Settled:
    forbidden = frozenset(names)
    slips = [
        f"{line.tool} at seq {line.seq}"
        for line in transcript.gate
        if line.kind == "tool.call" and line.tool in forbidden
    ]
    if slips:
        ruling = failing(f"the golden forbids {', '.join(names)}, and this call ran {'; '.join(slips)}")
    else:
        ruling = passing(f"none of the {len(names)} forbidden tool(s) ran")
    return Settled("not_tools", NOT_TOOLS, ruling)


def _check_says(transcript: judging.Transcript, phrases: Sequence[str]) -> Settled:
    turns = [turn.casefold() for turn in transcript.lines_by(judging.AGENT)]
    missing = [phrase for phrase in phrases if not any(phrase.casefold() in turn for turn in turns)]
    if missing:
        ruling = failing(f"the agent never said {', '.join(repr(phrase) for phrase in missing)}")
    else:
        ruling = passing(f"the agent said all {len(phrases)} expected phrase(s)")
    return Settled("says", SAYS, ruling)


def _check_says_any(transcript: judging.Transcript, phrases: Sequence[str]) -> Settled:
    turns = [turn.casefold() for turn in transcript.lines_by(judging.AGENT)]
    found = [phrase for phrase in phrases if any(phrase.casefold() in turn for turn in turns)]
    if found:
        ruling = passing(f"the agent said {found[0]!r}, one of the {len(phrases)} accepted")
    else:
        ruling = failing(f"the agent said none of {', '.join(repr(phrase) for phrase in phrases)}")
    return Settled("says_any", SAYS_ANY, ruling)


def _check_silence(transcript: judging.Transcript, phrases: Sequence[str]) -> Settled:
    turns = [turn.casefold() for turn in transcript.lines_by(judging.AGENT)]
    slips = [
        f"{phrase!r} in agent turn {number}"
        for phrase in phrases
        for number, turn in enumerate(turns, 1)
        if phrase.casefold() in turn
    ]
    if slips:
        ruling = failing(f"the golden forbids these and the agent said {'; '.join(slips)}")
    else:
        ruling = passing(f"none of the {len(phrases)} forbidden phrase(s) was said")
    return Settled("silence", SILENCE, ruling)


# Whole words only: `tu` is not `tutor`.
def _list_marks(turn: str, markers: frozenset[str]) -> list[str]:
    found: list[str] = []
    for word in turn.split():
        bare = word.strip(PUNCTUATION).casefold()
        if bare in markers and bare not in found:
            found.append(bare)
    return found
