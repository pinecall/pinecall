"""What a writer reads of an agent (prompt, tools, knowledge), and a library caller briefed on it before it phones."""

import logging
from collections.abc import Mapping
from dataclasses import replace
from functools import partial
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.calls import service as calls
from runtime.calls.log import Logs, Store
from runtime.evals.service.writers import Brief, write_scenario
from runtime.exceptions import PinecallError, QuotaExceeded
from runtime.judging import service as judging
from runtime.kit.crypto import Vault

logger = logging.getLogger(__name__)
NOT_BRIEFED = "caller %s not briefed on %s, played as written: %s"


class Describer(Protocol):
    """A domain above this one that holds agents' definitions, asked what one says of itself."""

    async def brief_of(self, session: AsyncSession, scope: Scope, slug: str) -> Brief | None:
        """What the agent says of itself, as a writer reads it; None for an agent this describer does not hold."""
        ...


# A class agent writes its prompt per call, so what it is about is read off its newest call. An
# agent built in Studio is a definition the gateway holds: its instructions and tools say what it does
# before anybody has called it, and the domain that holds them is above this one, so it is asked
# through here, as the lifespan wires it.
class Describers:
    """The describers wired at start, asked in turn; the first that knows the agent answers."""

    def __init__(self) -> None:
        self._each: list[Describer] = []

    def add(self, one: Describer) -> None:
        """One more domain that can describe an agent."""
        self._each.append(one)

    async def brief_of(self, session: AsyncSession, scope: Scope, slug: str) -> Brief | None:
        """The agent as the first describer that holds it says it; None when none does."""
        for one in self._each:
            told = await one.brief_of(session, scope, slug)
            if told is not None:
                return told
        return None


async def brief_of_agent(
    session: AsyncSession, describers: Describers, store: Store, prompts: judging.PromptTexts, scope: Scope, slug: str
) -> Brief:
    """The agent as a writer reads it: its definition where the gateway holds one, else off its newest call."""
    # An agent built in Studio says what it does before anybody calls it: its instructions and its tools.
    held = await describers.brief_of(session, scope, slug)
    if held is not None:
        return held
    declaration = await agents.declaration_of(session, scope, slug)
    newest = await calls.find_newest_call_of(session, scope, slug)
    prompt = ""
    if newest is not None:
        prompt = await judging.prompt_of(session, prompts, scope.org, await store.whole_of(newest))
    tools: tuple[str, ...] = ()
    if declaration is not None:
        tools = tuple(f"{tool.name}: {tool.description}" for tool in declaration.tools)
    knowledge = "" if declaration is None or declaration.knowledge is None else declaration.knowledge
    return Brief(prompt=prompt, tools=tools, knowledge=knowledge)


def as_scenario(caller: judging.Persona, goal: str, facts: Mapping[str, str]) -> judging.Persona:
    """The caller phoning about this, with these facts over its own: what a person wrote or chose before the call."""
    return replace(caller, goal=goal, facts={**caller.facts, **facts})


def is_from_the_library(caller: judging.Persona) -> bool:
    """A caller of Pinecall's library: written for every business, so it knows nothing of this one."""
    return caller.name in judging.library_personas()


# A caller of the library wants "help with what this business offers": played as written, it
# phones with nothing to say. Before the call it is briefed on the agent, as Generate reads it,
# by the judge model, as one eval; its manner, its facts and what it expects stay its own. The
# judge model is asked the one way it is asked outside a call (`judging.ask_judge_model`): until
# 2026-11 its eight steps were written here in line. An org out of evals is refused, as it was;
# any other failure plays the caller as written.
async def brief_persona(
    sessions: async_sessionmaker[AsyncSession],
    vault: Vault,
    describers: Describers,
    store: Store,
    prompts: judging.PromptTexts,
    logs: Logs,
    scope: Scope,
    slug: str,
    caller: judging.Persona,
) -> judging.Persona:
    """The caller with a goal for this agent, where it is the library's and the agent says anything; else as it came."""
    if not is_from_the_library(caller):
        return caller
    async with sessions.begin() as session:
        brief = await brief_of_agent(session, describers, store, prompts, scope, slug)
        declaration = await agents.declaration_of(session, scope, slug)
    if not brief.says_anything:
        return caller
    run = judging.JudgeRun("generate", "scenario", scope.env, evals=1)
    ask = partial(write_scenario, brief=brief, persona=caller)
    try:
        written, _spent = await judging.ask_judge_model(sessions, vault, scope, declaration, run, ask, logs.agent(slug))
    except QuotaExceeded:
        raise
    except PinecallError as failed:
        logger.warning(NOT_BRIEFED, caller.name, slug, failed)
        return caller
    return replace(caller, goal=written.goal, facts=dict(written.facts))
