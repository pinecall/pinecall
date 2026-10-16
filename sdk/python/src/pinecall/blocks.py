"""The prompt: four named blocks in two regions, in one order, and the page that prints them."""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from pinecall import _doc, _rules, _view
from pinecall.agent import Agent
from pinecall.call import Line
from pinecall.wire.parts import PromptBlockSpec, PromptRegion

# Every agent's blocks, in send order. The region boundary is the provider's cache boundary:
# never reorder them, and nothing but the view is dynamic.
LAYOUT: tuple[PromptBlockSpec, ...] = (
    PromptBlockSpec(name="identity", region="static"),
    PromptBlockSpec(name="knowledge", region="static"),
    PromptBlockSpec(name="tools", region="static"),
    PromptBlockSpec(name="view", region="dynamic"),
)


@dataclass(frozen=True)
class Block:
    """One named block of the prompt, its region, and its text."""

    name: str
    region: PromptRegion
    text: str


@dataclass(frozen=True)
class Blocks:
    """One rendered prompt: the blocks in send order, and the history between the two regions."""

    blocks: tuple[Block, ...]
    history: str

    def __getitem__(self, name: str) -> str:
        """The text of the block called `name`."""
        return next(block.text for block in self.blocks if block.name == name)

    def static(self) -> list[Block]:
        """The blocks before the history: what the provider caches."""
        return [block for block in self.blocks if block.region == "static"]

    def dynamic(self) -> list[Block]:
        """The blocks after the history: replaced every turn."""
        return [block for block in self.blocks if block.region == "dynamic"]

    def instructions(self) -> str:
        """The static blocks that say something, as one text."""
        return "\n\n".join(block.text for block in self.static() if block.text)


def render(
    agent: Agent,
    line: Line | None = None,
    *,
    resumed: bool = False,
    remembered: Sequence[str] = (),
) -> Blocks:
    """Render the agent's prompt in its state now, for the call `line` says.

    Args:
        agent: the agent, in the state the prompt is rendered for.
        line: the call; with none, the one the agent serves, else a phone call's.
        resumed: the call picks up one that was cut, which the view may say.
        remembered: the facts the runtime recalled about this caller; the view may ask
            `remembers("…")` of them and never prints one.
    """
    called = line or (agent.call.line() if agent.has_call else Line())
    texts = {
        "identity": identity(agent, called),
        # The gateway writes it from the agent's settings; the class sends nothing for it.
        "knowledge": "",
        "tools": tools(agent),
        "view": _view.rendered(
            type(agent), agent.snapshot(), called, resumed=resumed, remembered=remembered
        ),
    }
    blocks = tuple(Block(spec.name, spec.region, texts[spec.name]) for spec in LAYOUT)
    return Blocks(blocks, history(agent))


def identity(agent: Agent, line: Line) -> str:
    """The class's docstring, the framework's rules and protocols, and the channel's. No state."""
    channel = (
        tagged("channel", _rules.channel_rules_for(line.channel, line.medium))
        if type(agent).channel_rules
        else ""
    )
    said = [
        _doc.one_line(vars(type(agent)).get("__doc__")) or "",
        tagged("rules", _rules.RULES),
        tagged("protocols", _rules.PROTOCOLS),
        channel,
    ]
    return "\n\n".join(part for part in said if part.strip())


def tools(agent: Agent) -> str:
    """Every tool the class declares, seen or not, by name and description."""
    return tagged(
        "tools", "\n".join(f"- {spec.name}: {spec.description}" for spec in agent.tools())
    )


def history(agent: Agent) -> str:
    """The summaries `collapse` left; the turns themselves are the runtime's."""
    return "\n\n".join(
        f"{collapsed(change.seq)}\n{change.after}"
        for change in agent.changes()
        if change.field == "@summary"
    )


def collapsed(seq: int) -> str:
    """The marker where a stretch of the call was collapsed into one sentence."""
    return f"<!-- collapsed: {json.dumps({'seq': seq}, separators=(',', ':'))} -->"


def show_prompt(
    agent: Agent,
    line: Line | None = None,
    *,
    resumed: bool = False,
    remembered: Sequence[str] = (),
) -> str:
    """The prompt as one page, every block under its header, as `pinecall prompt` prints it."""
    rendered = render(agent, line, resumed=resumed, remembered=remembered)
    sections = [(header_for(block.name, block.region), block.text) for block in rendered.static()]
    sections.append((header_for("history"), rendered.history))
    sections += [(header_for(block.name, block.region), block.text) for block in rendered.dynamic()]
    return "\n\n".join(f"{header}\n{text}".rstrip() for header, text in sections)


def header_for(section: str, region: str | None = None) -> str:
    """One section's header on the printed page: `── view (dynamic) ──`."""
    named = section if region is None else f"{section} ({region})"
    return f"── {named} ──"


def tagged(name: str, body: str) -> str:
    """A body inside its tag, or nothing when there is no body."""
    return f"<{name}>\n{body}\n</{name}>" if body else ""
