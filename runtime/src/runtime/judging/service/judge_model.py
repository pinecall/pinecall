"""Which model judges an org's calls, on whose key and under what ceiling; and that model asked outside a call."""

import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.accounts import service as accounts
from runtime.actor import Scope
from runtime.agents import service as agents
from runtime.agents.declaration import Declaration
from runtime.billing import service as billing
from runtime.enums import Env, Stage
from runtime.exceptions import (
    Conflict,
    Forbidden,
    QuotaExceeded,
    ServiceUnavailable,
    UpstreamError,
    ValidationError,
)
from runtime.kit.crypto import Vault
from runtime.kit.text import JsonObject
from runtime.kit.time import epoch
from runtime.providers import service as providers
from runtime.providers.catalog import Catalog
from runtime.providers.stage import Model, Running
from runtime.wire.declaration import ModelConfig
from runtime.wire.metrics import LLMModelUsage
from runtime.wire.scores import EvalsSpent, SpentOn

NO_JUDGE = "this box's providers configuration names no judge model"
NO_CEILING = "the providers row gives the judge a ceiling of zero, so no judge model may be asked"
NO_LENT_CEILING = (
    "the judge model named runs on a key the platform lends, and the providers row gives the "
    "platform's judging no ceiling: name a model on a key of the org's own"
)
IN_THE_ENV = "{env} judges its calls on this model, and it cannot run there: {refused}"
# What the agent's log is written when a model is asked outside a call's score.
EVALS_SPENT = "evals.spent"


# Until 2026-11 "no judge model" was a model of None beside a sentence, built in seven places of
# the seal and read by comparing it to None in six more.
class Unjudged(ServiceUnavailable):
    """No judge model may be asked for the org, and the sentence says why."""


@dataclass(frozen=True, slots=True)
class JudgeModel:
    """The judge model a call is asked on, what one call may spend, and the org's evals left."""

    running: Running
    ceiling_usd: float
    # None: the org's evals are not counted against a limit.
    evals_left: int | None = None
    # The refusal of an org whose month's evals are used up: at hang-up its judges are skipped, and a
    # request outside a call is refused with it.
    exhausted: QuotaExceeded | None = None


@dataclass(frozen=True, slots=True)
class JudgeRun:
    """One request of the judge model outside a call: what it was for, where, the evals it is."""

    kind: SpentOn
    name: str
    env: Env
    evals: int
    calls: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Judging:
    """Whether an org's calls are judged at hang-up, on what model, and the ceiling per call."""

    on: bool
    ceiling_usd: float | None
    # The model the org's calls are judged on, an agent's own over it; None: the platform's.
    model: ModelConfig | None = None


# An agent's log is `calls`', above this domain: whoever asks the judge model outside a call hands in
# the log its spend is written on.
class SpendLog(Protocol):
    """The log of the agent a request of the judge model was made for."""

    async def append(self, type: str, data: JsonObject) -> object:
        """One entry on the agent's log."""
        ...


# What is asked of the judge model outside a call: given the model open, its answer and what it used.
type Ask[T] = Callable[[providers.Answerer], Awaitable[tuple[T, LLMModelUsage | None]]]


# The agent's model, else the org's, on the org's keys in the call's env: on its own key nothing
# is billed and no ceiling of the platform's applies; on a lent one the providers row's ceiling
# does. Neither named, the providers row's judge on the box's key.
async def judge_model_of(
    session: AsyncSession, vault: Vault, catalog: Catalog, scope: Scope, declaration: Declaration | None
) -> JudgeModel:
    """The judge model and its key for the scope's calls; Unjudged, saying why, when there is none."""
    named = None if declaration is None else declaration.judge
    if named is None:
        named = agents.read_model(await accounts.judge_model_of(session, scope.org), Stage.llm)
    if named is not None:
        keyring = await providers.keys_of(session, vault, scope)
        chosen = providers.stage_on_its_key(Stage.llm, named, catalog, keyring)
        if not chosen.lent:
            return JudgeModel(chosen, math.inf)
        if catalog.judge is None or catalog.judge.ceiling_usd <= 0:
            raise Unjudged(NO_LENT_CEILING)
        return await _on_a_lent_key(session, scope, chosen, catalog.judge.ceiling_usd)
    if catalog.judge is None:
        raise Unjudged(NO_JUDGE)
    if catalog.judge.ceiling_usd <= 0:
        raise Unjudged(NO_CEILING)
    box = await providers.box_credentials(session, vault)
    row = catalog.judge.llm
    # On the box's key as any stage is: with the row's options and request for that model, not bare.
    stage = providers.stage_on_its_key(
        Stage.llm, Model(vendor=row.vendor, model=row.model or ""), catalog, providers.Keyring(box=box)
    )
    return await _on_a_lent_key(session, scope, stage, catalog.judge.ceiling_usd)


# Priced by the names the operator configured, which the rates are keyed by. The rates are the
# providers row's: nothing here knows a price.
def price_of(spent: Sequence[LLMModelUsage], running: Running | None, catalog: Catalog) -> float:
    """What the judge model's requests cost at the providers row's rates, in dollars."""
    if running is None or not spent:
        return 0.0
    named = [
        usage.model_copy(update={"provider": running.vendor, "model": running.model or usage.model}) for usage in spent
    ]
    return providers.cost_of(named, catalog).usd


# On the org's own key the judge costs Pinecall nothing and counts no evals; on a lent one, the run
# counts the evals it was asked for.
def spend_of(run: JudgeRun, running: Running, catalog: Catalog, usage: LLMModelUsage | None) -> EvalsSpent:
    """What one request of the judge model cost, as the org's usage counts it."""
    cost = price_of([usage] if usage else [], running, catalog)
    own = not running.lent
    return EvalsSpent(
        kind=run.kind,
        name=run.name,
        env=run.env,
        calls=list(run.calls),
        evals=0 if own else run.evals,
        judge_calls=1,
        judge_cost_usd=cost or None,
        own_key=own,
    )


# The one way the judge model is asked outside a call. Until 2026-11 these steps were written four
# times, three of them in the bodies of endpoints, each reading the org's evals twice. The model is
# read in a transaction of its own and asked with no connection held; `count` says the evals an
# answer is where the answer decides it (one a persona written).
async def ask_judge_model[T](
    sessions: async_sessionmaker[AsyncSession],
    vault: Vault,
    scope: Scope,
    declaration: Declaration | None,
    run: JudgeRun,
    ask: Ask[T],
    log: SpendLog,
    *,
    count: Callable[[T], int] | None = None,
) -> tuple[T, EvalsSpent]:
    """Ask the judge model of the scope's calls one thing outside a call; the answer, and its spend written."""
    async with sessions.begin() as session:
        catalog = await providers.get_catalog(session)
        judge = await judge_model_of(session, vault, catalog, scope, declaration)
    if judge.exhausted is not None:
        raise judge.exhausted
    async with providers.open_answerer(judge.running) as model:
        answer, usage = await ask(model)
    billed = run if count is None else replace(run, evals=count(answer))
    spent = spend_of(billed, judge.running, catalog, usage)
    await log.append(EVALS_SPENT, spent.dump())
    return answer, spent


# ── the org's switch ──


# Per org, not per env: an org's evals are counted across both. The switch and the model are two
# columns of `orgs`, which is accounts' table: read and written through its service.
async def judging_of(session: AsyncSession, org: str) -> Judging:
    """Whether the org's hang-up judging is on, the model it runs on, and its ceiling per call."""
    catalog = await providers.get_catalog(session)
    return Judging(
        on=await accounts.is_judged(session, org),
        ceiling_usd=providers.judge_ceiling(catalog),
        model=await accounts.judge_model_of(session, org),
    )


# The model is tried on the org's keys in each env, since both judge their calls on it: one the org
# cannot key there, a plugin of its own on a lent key, or a model its vendor turns away, is refused
# naming the env; asked once for each key it would run on, in the words of the vendor's no. The
# keys are read in a transaction of their own, and the vendor asked with no connection held.
async def put_judging(
    sessions: async_sessionmaker[AsyncSession], vault: Vault, org: str, *, on: bool, model: ModelConfig | None
) -> Judging:
    """Hang-up judging on or off, and the model it runs on, from the next call."""
    named = agents.read_model(model, Stage.llm)
    if named is not None:
        async with sessions.begin() as session:
            catalog = await providers.get_catalog(session)
            keyrings = {env: await providers.keys_of(session, vault, Scope(org, env)) for env in Env}
        tried: list[Running] = []
        for env, keyring in keyrings.items():
            try:
                stage = providers.stage_on_its_key(Stage.llm, named, catalog, keyring)
                if stage not in tried:
                    await providers.try_stage(Stage.llm, stage, what=f"the judge model {_name_of(named)}")
                    tried.append(stage)
            except (Forbidden, ServiceUnavailable, Conflict, ValidationError, UpstreamError) as refused:
                raise type(refused)(IN_THE_ENV.format(env=env.value, refused=refused)) from refused
    async with sessions.begin() as session:
        await accounts.set_judging(session, org, on=on)
        await accounts.set_judge_model(session, org, model)
        return await judging_of(session, org)


# ── private ──


# Read once a call: the panel spends what is left in its order, and a refusal is a judge skipped.
async def _on_a_lent_key(session: AsyncSession, scope: Scope, running: Running, ceiling_usd: float) -> JudgeModel:
    try:
        left = await billing.admit_evals(session, scope.org, scope.env, at=epoch())
    except QuotaExceeded as exhausted:
        return JudgeModel(running, ceiling_usd, evals_left=0, exhausted=exhausted)
    return JudgeModel(running, ceiling_usd, evals_left=left)


def _name_of(model: Model) -> str:
    return f"{model.vendor}/{model.model}" if model.model else model.vendor
