"""What a writer reads of an agent — prompt, tools, knowledge — and a library caller briefed on it before it phones."""

import logging
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls import service as calls
from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.time import epoch
from pinecall_runtime.providers import service as providers

logger = logging.getLogger(__name__)
NOT_BRIEFED = "caller %s not briefed on %s, played as written: %s"


async def brief_of_agent(session: AsyncSession, serving: calls.Serving, scope: Scope, slug: str) -> judging.Brief:
    """The agent as a writer reads it: its definition where the gateway holds one, else off its newest call."""
    # An agent built in Studio says what it does before anybody calls it: its instructions and its tools.
    held = await serving.describers.brief_of(session, scope, slug)
    if held is not None:
        return held
    registration = serving.registry.serving(scope, slug, None)
    declared = None if registration is None else registration.config
    newest = await calls.find_calls(session, scope, calls.ListFilters(agent=slug), limit=1)
    prompt = ""
    if newest.calls:
        prompt = await calls.prompt_of(session, scope.org, await serving.logs.store.whole(newest.calls[0]))
    tools: tuple[str, ...] = ()
    if declared is not None:
        tools = tuple(f"{tool.name}: {tool.description}" for tool in declared.tools)
    knowledge = "" if declared is None or declared.knowledge is None else declared.knowledge
    return judging.Brief(prompt=prompt, tools=tools, knowledge=knowledge)


def says_anything(brief: judging.Brief) -> bool:
    """Whether the brief says a word of the agent: one nobody has called, with no tools, is nothing to brief on."""
    return bool(brief.prompt or brief.tools or brief.knowledge)


def as_scenario(caller: judging.CallerPersona, goal: str, facts: Mapping[str, str]) -> judging.CallerPersona:
    """The caller phoning about this, with these facts over its own: what a person wrote or chose before the call."""
    return caller.model_copy(update={"goal": goal, "facts": {**caller.facts, **facts}})


def is_the_librarys(caller: judging.CallerPersona) -> bool:
    """A caller of Pinecall's library: written for every business, so it knows nothing of this one."""
    return caller.name in judging.library_personas()


# A caller of the library wants "help with what this business offers": played as written, it
# phones with nothing to say. Before the call it is briefed on the agent, as Generate reads it,
# by the judge model, as one eval; its manner, its facts and what it expects stay its own.
async def briefed(
    session: AsyncSession, serving: calls.Serving, scope: Scope, slug: str, caller: judging.CallerPersona
) -> judging.CallerPersona:
    """The caller with a goal for this agent, where it is the library's and the agent says anything; else as it came."""
    if not is_the_librarys(caller):
        return caller
    brief = await brief_of_agent(session, serving, scope, slug)
    if not says_anything(brief):
        return caller
    registration = serving.registry.serving(scope, slug, None)
    declared = None if registration is None else registration.config
    configured = await providers.get_catalog(session)
    judge = await calls.judge_of(session, serving, configured, scope, declared)
    if judge.running is None:
        return caller
    if judge.running.lent:
        await billing.admit_evals(session, scope.org, scope.env, at=epoch())
    persona = judging.Persona(
        name=caller.name,
        goal=caller.goal,
        style=caller.style,
        facts={name: str(value) for name, value in caller.facts.items()},
        expects=tuple(caller.expects),
        behavior=judging.Behavior(**caller.behavior.model_dump()),
    )
    model = providers.llm_of(judge.running)
    try:
        written, usage = await judging.write_scenario(model, brief, persona)
    except PinecallError as failed:
        logger.warning(NOT_BRIEFED, caller.name, slug, failed)
        return caller
    finally:
        await model.aclose()
    run = judging.JudgeRun("generate", "scenario", scope.env, evals=1, calls=())
    spent = judging.judge_spend(run, judge.running, configured, usage)
    await serving.logs.agent(slug).append("evals.spent", spent.dump())
    return caller.model_copy(update={"goal": written.goal, "facts": dict(written.facts)})
