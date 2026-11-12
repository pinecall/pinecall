"""A team of agents one call passes between: the tools offering the pass, and who answers first."""

import asyncio
import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from pinecall import _tools
from pinecall.call import CallLine
from pinecall.errors import DeclarationRefused
from pinecall.wire.parts import ToolSpec

MOST_PASSES = 3
"""How many times one call is passed before the next pass is refused."""

PASSED = "handoff"
"""The custom entry a pass leaves on its call."""

ROUTED = "routed"
"""The custom entry a call leaves when its line's `answers` chose who serves it, or could not."""

ANSWERED_WITHIN_S = 1.0
"""How long a line's `answers` has to choose: the caller is hearing the greeting meanwhile."""

TRANSFER = "transfer_to_"

Answering = Callable[[CallLine], "type | Awaitable[type | None] | None"]
"""A line's `answers` as a function: the agent of the team that serves this call, or None."""

Team = Mapping[type, str]
"""The agents a call may pass between, each with the slug it is served as."""


@dataclass(frozen=True)
class Answered:
    """Who serves a call whose line chooses, and why it is not the one chosen, when it is not."""

    agent: type
    why: str | None = None


async def answered_by(answers: Answering, line: CallLine, bound: type, team: Team) -> Answered:
    """What `answers` chose when it is of the team and came in time, else `bound`; never raises."""
    try:
        chosen = await asyncio.wait_for(_chosen(answers, line), ANSWERED_WITHIN_S)
    except TimeoutError:
        return Answered(bound, f"answers took more than {ANSWERED_WITHIN_S:g} s")
    except Exception as failed:  # noqa: BLE001 - a tenant's function failing still answers the call
        return Answered(bound, f"answers raised: {failed}")
    if chosen is None or chosen is bound:
        return Answered(bound)
    if chosen not in team:
        name = getattr(chosen, "__name__", repr(chosen))
        return Answered(bound, f"answers chose {name}, which is not of the line's team")
    return Answered(chosen)


async def _chosen(answers: Answering, line: CallLine) -> type | None:
    chosen = answers(line)
    if inspect.isawaitable(chosen):
        return await chosen
    return chosen


def taken_by(cls: type) -> str | None:
    """What a class says it takes, in the words a model reads to choose it."""
    takes: object = getattr(cls, "takes", None)
    return takes.strip() if isinstance(takes, str) and takes.strip() else None


def transfer_name(mate: type) -> str:
    """The tool a teammate is offered by: named by its class, which the model reads."""
    return TRANSFER + re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", mate.__name__).lower()


def transfers_of(cls: type, team: Team) -> list[ToolSpec]:
    """The tools that offer a call of `cls` to each teammate that says what it takes."""
    offered: list[ToolSpec] = []
    for mate in team:
        takes = taken_by(mate)
        if mate is cls or takes is None:
            continue
        offered.append(
            ToolSpec(
                name=transfer_name(mate),
                description=(
                    f"Pass the call to {mate.__name__}, who takes {takes}. Call it as soon as the"
                    " caller brings that up: do not ask them first, and do not answer it yourself."
                    " The caller is not told about the pass."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "Why, in a few words."}
                    },
                    "required": [],
                },
            )
        )
    return offered


def mate_named(tool: str, team: Team) -> type | None:
    """The teammate a transfer tool names."""
    return next((mate for mate in team if transfer_name(mate) == tool), None)


def team_tools(team: Team) -> list[ToolSpec]:
    """Every tool a call of the team may open; a name two members declare is refused."""
    owners: dict[str, str] = {}
    declared: list[ToolSpec] = []
    for member, slug in team.items():
        own: dict[str, _tools.Declared] = getattr(member, "_pinecall_tools", {})
        for spec in [*(one.spec for one in own.values()), *transfers_of(member, team)]:
            owner = owners.get(spec.name)
            if owner == slug or (owner is not None and spec.name.startswith(TRANSFER)):
                continue
            if owner is not None:
                raise DeclarationRefused(
                    f"{owner} and {slug} both declare a tool named {spec.name}:"
                    " the agents of one team give each tool a name of its own"
                )
            owners[spec.name] = slug
            declared.append(spec)
    return declared
