"""What a golden holds a call to: the judges its final expect sets, and the lookup its facts answer."""

from collections.abc import Awaitable, Callable, Mapping, Sequence

from pinecall_runtime.judging.service.case import AGENT, PUNCTUATION, Case, calls_of, said_by
from pinecall_runtime.judging.service.panel import CaseJudge, GoldenJudge, failing, passing
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.session import service as session
from pinecall_runtime.wire.events import MemoryOps
from pinecall_runtime.wire.goldens import Golden, Register
from pinecall_runtime.wire.parts import MemoryFact, MemoryOp, PlatformTool

# The source of a golden's facts, so the log never passes them off as real memory.
A_GOLDEN = "golden"

# What a lookup writes on the call's log: the entry's type and its data.
type Writes = Callable[[str, JsonObject], Awaitable[object]]

TOOLS = "Every tool this golden names was called in the conversation."
NOT_TOOLS = "The conversation called none of the tools this golden forbids."
SAYS = "The agent said every phrase this golden names."
SAYS_ANY = "The agent said at least one of the phrases this golden accepts."
SILENCE = "The agent said none of the phrases this golden names."
REGISTER = "The agent addressed the caller as {register} in every one of its turns."
ON_THE_PANEL = "The judge {name} held of this call."
# A check that could not look must not pass: a judge nobody wrote breaks the golden.
NOT_ON_THE_PANEL = "this golden asks {name}, and there is no such judge: there are {panel}"

# Unmistakable tú; `té` (tea) carries its accent, so `te` never matches it.
TUTEO: frozenset[str] = frozenset({"tú", "ti", "te", "contigo", "tu", "tus", "tuyo", "tuya", "tuyos", "tuyas"})
# `le`, `les`, `su` and `sus` are left out: they are as often the third person.
USTEO: frozenset[str] = frozenset({"usted", "ustedes", "consigo", "suyo", "suya", "suyos", "suyas"})


# `panel` is every judge the agent's calls may meet, the library's and the org's own, by name.
def golden_judges(golden: Golden, case: Case, panel: Mapping[str, GoldenJudge] | None = None) -> list[GoldenJudge]:
    """One judge per field of the final expect, then the judges it names, from `panel`."""
    expect = golden.expect
    panel = panel or {}
    judges: list[GoldenJudge] = []
    if expect.tools:
        judges.append(_tools(case, expect.tools))
    if expect.not_tools:
        judges.append(_not_tools(case, expect.not_tools))
    if expect.not_said:
        judges.append(_silence(case, expect.not_said))
    if expect.says:
        judges.append(_says(case, expect.says))
    if expect.says_any:
        judges.append(_says_any(case, expect.says_any))
    if expect.grounded:
        judges.append(_on_the_panel(panel, "grounded"))
    if expect.addressed_as is not None:
        judges.append(_register_judge(case, expect.addressed_as))
    present = {judge.name for judge in judges}
    judges.extend(_on_the_panel(panel, name) for name in expect.judges if name not in present)
    return judges


# recall reads the golden's facts and nothing else; search is the real index, since that is what
# the golden is asking about. The recall is written as a real one is, so the app learns the facts.
def golden_lookup(facts: Sequence[str], search: session.Lookup, wrote: Writes) -> session.Lookup:
    """The lookup a golden's call runs: recall answered by its facts, search by the index."""

    async def lookup(tool: PlatformTool, arguments: JsonObject, speech: str | None) -> JsonObject:
        if tool != "recall":
            return await search(tool, arguments, speech)
        recalled = [MemoryFact(text=fact, source=A_GOLDEN) for fact in facts]
        query = arguments.get("query")
        op = MemoryOp(op="recall", query=str(query) if query else None, facts=recalled, took_ms=0.0)
        await wrote("memory.ops", MemoryOps(ops=[op], speech_id=speech).dump())
        return {"facts": [{"text": fact, "source": A_GOLDEN} for fact in facts]}

    return lookup


def _on_the_panel(panel: Mapping[str, GoldenJudge], name: str) -> GoldenJudge:
    """The judge of that name, or one that breaks saying there is none."""
    found = panel.get(name)
    if found is not None:
        return found
    names = ", ".join(panel) or "no judge at all"
    ruling = failing(NOT_ON_THE_PANEL.format(name=name, panel=names))
    return CaseJudge(name, ON_THE_PANEL.format(name=name), ruling)


def _register_judge(case: Case, expected: Register) -> CaseJudge:
    """Whether the agent never used the other register's words."""
    other = USTEO if expected == "tu" else TUTEO
    turns = said_by(case, AGENT)
    slips = [(number, word) for number, turn in enumerate(turns, 1) for word in _marked(turn, other)]
    if slips:
        spoken = "; ".join(f"{word!r} in agent turn {number}" for number, word in slips)
        ruling = failing(f"the agent was asked for {expected} and said {spoken}")
    else:
        ruling = passing(f"no word of the other register in {len(turns)} agent turn(s), asked for {expected}")
    return CaseJudge("register", REGISTER.format(register=expected), ruling)


# The order the tools ran in is not judged.
def _tools(case: Case, names: Sequence[str]) -> CaseJudge:
    ran = {called.name for called in calls_of(case)}
    missing = [name for name in names if name not in ran]
    if missing:
        what_ran = ", ".join(sorted(ran)) or "no tool at all"
        ruling = failing(f"the golden expects {', '.join(missing)}, and this call ran {what_ran}")
    else:
        ruling = passing(f"every expected tool ran: {', '.join(names)}")
    return CaseJudge("tools", TOOLS, ruling)


def _not_tools(case: Case, names: Sequence[str]) -> CaseJudge:
    forbidden = frozenset(names)
    slips = [
        f"{line.tool} at seq {line.seq}" for line in case.gate if line.kind == "tool.call" and line.tool in forbidden
    ]
    if slips:
        ruling = failing(f"the golden forbids {', '.join(names)}, and this call ran {'; '.join(slips)}")
    else:
        ruling = passing(f"none of the {len(names)} forbidden tool(s) ran")
    return CaseJudge("not_tools", NOT_TOOLS, ruling)


def _says(case: Case, phrases: Sequence[str]) -> CaseJudge:
    turns = [turn.casefold() for turn in said_by(case, AGENT)]
    missing = [phrase for phrase in phrases if not any(phrase.casefold() in turn for turn in turns)]
    if missing:
        ruling = failing(f"the agent never said {', '.join(repr(phrase) for phrase in missing)}")
    else:
        ruling = passing(f"the agent said all {len(phrases)} expected phrase(s)")
    return CaseJudge("says", SAYS, ruling)


def _says_any(case: Case, phrases: Sequence[str]) -> CaseJudge:
    turns = [turn.casefold() for turn in said_by(case, AGENT)]
    found = [phrase for phrase in phrases if any(phrase.casefold() in turn for turn in turns)]
    if found:
        ruling = passing(f"the agent said {found[0]!r}, one of the {len(phrases)} accepted")
    else:
        accepted = ", ".join(repr(phrase) for phrase in phrases)
        ruling = failing(f"the agent said none of {accepted}")
    return CaseJudge("says_any", SAYS_ANY, ruling)


def _silence(case: Case, phrases: Sequence[str]) -> CaseJudge:
    turns = [turn.casefold() for turn in said_by(case, AGENT)]
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
    return CaseJudge("silence", SILENCE, ruling)


# Whole words only: `tu` is not `tutor`.
def _marked(turn: str, markers: frozenset[str]) -> list[str]:
    found: list[str] = []
    for word in turn.split():
        bare = word.strip(PUNCTUATION).casefold()
        if bare in markers and bare not in found:
            found.append(bare)
    return found
