"""How a call ends: what it taught memory, what it cost, how it was judged, and its log sealed."""

import asyncio
import logging
import math
import time
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.agents.declaration import AgentConfig
from pinecall_runtime.agents.service import prompts, tuning
from pinecall_runtime.alerts import service as alerts
from pinecall_runtime.billing import service as billing
from pinecall_runtime.calls.latencies import phone_legs
from pinecall_runtime.calls.logs import Log
from pinecall_runtime.calls.reducer import reduce
from pinecall_runtime.calls.repository.facts import FactsRepository
from pinecall_runtime.calls.repository.heads import HeadRepository
from pinecall_runtime.calls.repository.spend import SpendRepository
from pinecall_runtime.calls.schemas import SealCallRequest
from pinecall_runtime.calls.service import drift, usage
from pinecall_runtime.calls.service.live import Served
from pinecall_runtime.calls.service.serving import Serving
from pinecall_runtime.calls.store import Store
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.exceptions import PinecallError, QuotaExceeded, ServiceUnavailable
from pinecall_runtime.judging import service as judging
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.knowledge import service as knowledge
from pinecall_runtime.providers import service as providers
from pinecall_runtime.telephony import service as telephony
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import CallEnded, CallStarted, CallSummary, ErrorEvent, MemoryOps
from pinecall_runtime.wire.parts import MemoryOp
from pinecall_runtime.wire.scores import CallScore
from pinecall_runtime.wire.state import AgentTurn

logger = logging.getLogger(__name__)

JUDGING_OFF = "this org's calls are not judged at hang-up: POST /v1/evals/judge/{call} judges one"
A_RUN_JUDGES_IT = "an eval run opened this call, and its own judges scored it in the run's matrix"
NO_JUDGE = "this box's providers configuration names no judge model"
NO_CEILING = "the providers row gives the judge a ceiling of zero, so no judge model may be asked"
NO_LENT_CEILING = (
    "the judge model named runs on a key the platform lends, and the providers row gives the "
    "platform's judging no ceiling: name a model on a key of the org's own"
)

# What a hang-up waits for the one model call that writes memory, unless the settings say.
REMEMBER_BUDGET_S = 8.0

# How long one gateway holds the right to seal a call, renewed at a third of it while it seals:
# a gateway that dies sealing lets the call go within these seconds, and a request waiting on it
# takes the seal over. Held 120 s unrenewed, a worker gave up (30 s) on a call whose sealing
# gateway died, and the reaper sealed it later with no usage: measured with a gateway killed
# every minute.
LEASED_S = 15.0
LOOKED_AGAIN_S = 0.5
# How long a request waits on another gateway's seal before it says so: the worker asks again.
WAITED_AT_MOST_S = 25.0


class SealedElsewhere(ServiceUnavailable):
    """Another gateway is sealing the call and has not finished."""

    def __init__(self, call: str) -> None:
        super().__init__(f"call {call} is being sealed by another gateway, which has not finished: ask again")


# One end for every call: a worker's, a written one's, and one the reaper finishes. A call is
# sealed once: a second request waits for the first and finds the call gone, and a seal that
# broke after its summary goes on from the score, so no call is remembered or billed twice.
# Across gateways the head's lease does what the lock does here: a request that finds it taken
# waits for the log to say sealed.
async def seal(serving: Serving, served: Served, sealing: SealCallRequest, *, lent: Sequence[str] = ()) -> None:
    """Remember, price the call, write its summary and its score, seal the log, let it go."""
    async with served.sealing:
        if served.call not in serving.live.calls:
            return
        store = serving.logs.store
        if not await store.lease_seal(served.call, LEASED_S) and await _sealed_elsewhere(serving, served):
            return
        renewing = asyncio.create_task(_renew(store, served.call))
        try:
            entries = await store.whole(served.call)
            if all(entry.type != "call.summary" for entry in entries):
                await _price(serving, served, sealing, lent)
            score = await _score(serving, served)
            await served.log.append("call.score", score.dump())
        except BaseException:
            await store.release_seal(served.call)
            raise
        finally:
            renewing.cancel()
            await asyncio.gather(renewing, return_exceptions=True)
        async with serving.handles.sessions.begin() as session:
            await drift_folded(session, served.call, entries, score)
            await _keep_as_case(session, serving, served, score)
            at = serving.logs.store.clock()
            await alerts.watch_spend(
                session,
                serving.handles,
                serving.logs,
                serving.counters,
                served.scope,
                served.agent,
                ledger=SpendRepository(session),
                at=at,
            )
            await alerts.check_monitors(
                session, serving.handles, serving.logs, served.scope, served.agent, series=usage.series_window, at=at
            )
        serving.logs.forget(served.call)
        serving.live.close_call(served.call)


# Between call.ended and call.summary, on the org's keys as they are now. A refusal at the cap
# goes on the agent's log and the call's says an empty remember; a break is an entry, and it seals.
async def remember(session: AsyncSession, serving: Serving, served: Served) -> knowledge.MemoryWrite | None:
    """What the call taught its contact's memory, written; None when the agent keeps nothing."""
    entries = await serving.logs.store.whole(served.call)
    heard = knowledge.heard_in(
        served.call, served.context.channel, served.context.remembered_as, served.config, entries, at=serving.now
    )
    if heard is None or serving.embedder is None:
        return None
    try:
        kept = await knowledge.facts_kept(session, served.scope.org, served.scope.env)
        await billing.admit_memory(session, served.scope.org, served.scope.env, kept=kept)
    except QuotaExceeded as refused:
        await alerts.credits_exhausted(session, serving.handles, serving.logs, served.scope, served.agent, refused)
        op = MemoryOp(op="remember", contact=heard.contact, facts=[], took_ms=0.0)
        await served.log.append("memory.ops", MemoryOps(ops=[op]).dump())
        return knowledge.MemoryWrite(op=op, usage=None)
    budget = serving.handles.settings.remember_budget_s or REMEMBER_BUDGET_S
    try:
        async with asyncio.timeout(budget):
            catalog = await providers.get_catalog(session)
            keys = await providers.keys_of(session, serving.handles.vault, served.scope)
            model = providers.thinking_of(served.config, catalog, keys)
            written = await knowledge.remember(session, serving.embedder, model, served.scope, heard)
    except Exception as broke:
        # Memory is a courtesy to the next call; this one ends all the same.
        logger.warning("call %s was not written into memory", served.call, exc_info=True)
        why = f"the call was not written into memory: {broke or type(broke).__name__}"
        await served.log.append("error", ErrorEvent(code="remember_failed", message=why, recoverable=True).dump())
        return None
    await served.log.append("memory.ops", MemoryOps(ops=[written.op]).dump())
    return written


# The seal never fails on a judge: a call that could not be judged says why and seals all the same.
async def judge_call(
    session: AsyncSession,
    serving: Serving,
    entries: Sequence[Entry],
    declared: AgentConfig | None,
    panel: judging.Panel,
    scope: Scope,
) -> CallScore:
    """The panel over a finished call: the library's judges switched on, then the org's own."""
    call = next((entry.call for entry in entries if entry.call is not None), "")
    try:
        catalog = await providers.get_catalog(session)
        judge = await judge_of(session, serving, catalog, scope, declared)
        return await judging.judge_at_hangup(entries, declared, panel, judge, configured=catalog)
    except PinecallError as broke:
        logger.warning("call %s: nothing judged it", call, exc_info=True)
        return CallScore(judges=[], judge_calls=0, not_judged=f"judging this call failed: {broke}")


async def panel_for(
    session: AsyncSession, org: str, entries: Sequence[Entry], declared: AgentConfig | None
) -> judging.Panel:
    """What a call is judged by: the switches, the org's own judges, what the judges are told."""
    call = next((entry.call for entry in entries if entry.call is not None), "")
    agent = entries[0].agent if entries else ""
    return judging.Panel(
        switches=await judging.switches_for(session, org, agent),
        own=await judging.own_judges_for(session, org, agent),
        around=await surroundings_of(session, org, call, declared),
        prompt=await prompt_of(session, org, entries),
    )


# The org as the call spoke for it: its name, the opening sentence it set, and an opt-out it took.
async def surroundings_of(
    session: AsyncSession, org: str, call: str, declared: AgentConfig | None
) -> judging.Surroundings:
    """What the judges that read facts are told beyond the call's log."""
    found = await orgs.find_org(session, org)
    name = org if found is None else found.name
    kept = (await compliance.policy_of(session, org)).policy
    language = None if declared is None else declared.language
    opening = compliance.disclosure_of(kept, name, language)
    return judging.Surroundings(org=name, disclosure=opening, opted_out=await telephony.opted_out_on(session, call))


# Each block's last text, as the call's last turn was told it; a block the org never kept is
# left out rather than guessed.
async def prompt_of(session: AsyncSession, org: str, entries: Sequence[Entry]) -> str:
    """The prompt the call ran on, block by block, for a judge that reads the agent's prompt."""
    latest: dict[str, str] = {}
    for entry in entries:
        if entry.type == "prompt.changed":
            latest[str(entry.data["name"])] = str(entry.data["hash"])
    texts = await prompts.texts_of(session, org, set(latest.values()))
    return "\n\n".join(f"## {name}\n{texts[kept]}" for name, kept in latest.items() if kept in texts)


# The agent's model, else the org's, on the org's keys in the call's env: on its own key nothing
# is billed and no ceiling of the platform's applies; on a lent one the providers row's ceiling
# does. Neither named, the providers row's judge on the box's key.
async def judge_of(
    session: AsyncSession, serving: Serving, catalog: providers.Catalog, scope: Scope, declared: AgentConfig | None
) -> judging.JudgeModel:
    """The judge model and its key, or None and the sentence that says why there is none."""
    vault = serving.handles.vault
    named = None if declared is None else declared.judge
    if named is None:
        named = tuning.model_from_wire(await orgs.judge_model_of(session, scope.org), "llm")
    if named is not None:
        keyring = await providers.keys_of(session, vault, scope)
        chosen = providers.stage_on_its_key("llm", named, catalog, keyring)
        if not chosen.lent:
            return judging.JudgeModel(chosen, math.inf)
        if catalog.judge is None or catalog.judge.ceiling_usd <= 0:
            return judging.JudgeModel(None, 0.0, NO_LENT_CEILING)
        return judging.JudgeModel(chosen, catalog.judge.ceiling_usd, evals_left=await _evals_left(session, scope))
    if catalog.judge is None:
        return judging.JudgeModel(None, 0.0, NO_JUDGE)
    if catalog.judge.ceiling_usd <= 0:
        return judging.JudgeModel(None, 0.0, NO_CEILING)
    box = await providers.box_credentials(session, vault)
    row = catalog.judge.llm
    stage = providers.running_on(providers.Keyring(box=box), row.vendor, row.model or None)
    return judging.JudgeModel(stage, catalog.judge.ceiling_usd, evals_left=await _evals_left(session, scope))


# Drift is a measure of the day, not of the call: a fold that breaks is logged and the call seals
# all the same, and `pinecall-runtime drift rebuild` counts it later.
async def drift_folded(session: AsyncSession, call: str, entries: Sequence[Entry], score: CallScore) -> None:
    """Count the call's stages and verdicts into its day's drift, or log why not."""
    try:
        async with session.begin_nested():
            await drift.fold(session, call, entries, score)
    except SQLAlchemyError:
        logger.warning("call %s was not counted into its day's drift", call, exc_info=True)


async def sum_up(session: AsyncSession, store: Store, log: Log, sealing: SealCallRequest) -> None:
    """call.summary: how the call ended, what it used, what that cost."""
    entries = await store.whole(log.name)
    ended = next((entry for entry in reversed(entries) if entry.type == "call.ended"), None)
    over = None if ended is None else CallEnded.model_validate(ended.data)
    state = reduce(entries)
    duration = 0.0 if over is None else over.duration_s
    catalog = await providers.get_catalog(session)
    summary = CallSummary(
        reason="error" if over is None else over.reason,
        outcome=sealing.outcome,
        duration_s=duration,
        turns=sum(1 for turn in state.turns if isinstance(turn, AgentTurn)),
        usage=sealing.usage,
        cost=providers.cost_of(sealing.usage, catalog, legs=phone_legs(entries), seconds=duration),
        recording=sealing.recording,
        simulated=judging.is_simulated(entries),
        run=_run_of(entries),
    )
    # Once per log: two gateways sealing one call (a lease lapsed under a stalled seal) price it once.
    await log.append_first("call.summary", summary.dump())


async def _price(serving: Serving, served: Served, sealing: SealCallRequest, lent: Sequence[str]) -> None:
    async with serving.handles.sessions.begin() as session:
        written = await remember(session, serving, served)
        # The memory model's tokens are the call's: they are billed with it.
        if written is not None and written.usage is not None:
            sealing = sealing.model_copy(update={"usage": [*sealing.usage, written.usage]})
        await sum_up(session, serving.logs.store, served.log, sealing)
        if lent:
            await FactsRepository(session).set_lent(served.call, lent)


async def _score(serving: Serving, served: Served) -> CallScore:
    if served.context.run is not None:
        return CallScore(judges=[], judge_calls=0, not_judged=A_RUN_JUDGES_IT)
    async with serving.handles.sessions.begin() as session:
        if not await orgs.is_judged(session, served.scope.org):
            return CallScore(judges=[], judge_calls=0, not_judged=JUDGING_OFF.format(call=served.call))
        entries = await serving.logs.store.whole(served.call)
        panel = await panel_for(session, served.scope.org, entries, served.config)
        score = await judge_call(session, serving, entries, served.config, panel, served.scope)
        if any(judgment.reason == judging.OUT_OF_EVALS for judgment in score.judges):
            limit = (await billing.get_quotas(session, served.scope.org, served.scope.env)).evals or 0
            refused = QuotaExceeded(judging.OUT_OF_EVALS, quota="evals", used=limit, limit=limit)
            await alerts.credits_exhausted(session, serving.handles, serving.logs, served.scope, served.agent, refused)
    return score


# True once another gateway sealed it; False when its lease ran out (that gateway died sealing)
# and this one took it over, so the caller seals.
async def _sealed_elsewhere(serving: Serving, served: Served) -> bool:
    store = serving.logs.store
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAITED_AT_MOST_S
    while not await store.is_sealed(served.call):
        if await store.lease_seal(served.call, LEASED_S):
            return False
        if loop.time() > deadline:
            raise SealedElsewhere(served.call)
        await asyncio.sleep(LOOKED_AGAIN_S)
    serving.logs.forget(served.call)
    serving.live.close_call(served.call)
    return True


async def _renew(store: Store, call: str) -> None:
    while True:
        await asyncio.sleep(LEASED_S / 3)
        await store.renew_seal(call, LEASED_S)


# A call a judge broke on waits in the org's inbox as a case. Like drift, it is kept after the
# call: a write that breaks is logged and the call seals all the same.
async def _keep_as_case(session: AsyncSession, serving: Serving, served: Served, score: CallScore) -> None:
    if score.passed is not False:
        return
    try:
        async with session.begin_nested():
            entries = await serving.logs.store.whole(served.call)
            kept = await HeadRepository(session).head_of_call(served.call)
            version = None if kept is None else kept.versions.config
            await judging.keep_at_hangup(
                session, entries, score, judging.Born(served.scope.org, served.scope.env, served.agent, version)
            )
    except SQLAlchemyError:
        logger.warning("call %s was not kept as a case", served.call, exc_info=True)


def _run_of(entries: Sequence[Entry]) -> str | None:
    started = next((entry for entry in entries if entry.type == "call.started"), None)
    return None if started is None else CallStarted.model_validate(started.data).run


# Read once a call: the panel spends what is left in its order, and a refusal is a judge skipped.
async def _evals_left(session: AsyncSession, scope: Scope) -> int | None:
    try:
        return await billing.admit_evals(session, scope.org, scope.env, at=time.time())
    except QuotaExceeded:
        return 0
