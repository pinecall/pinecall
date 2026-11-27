"""A flow's model, asked outside a call: words read into the object a JSON Schema says, and what it spent."""

from dataclasses import dataclass
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.billing import service as billing
from runtime.calls import service as calls
from runtime.enums import Stage
from runtime.exceptions import Conflict, UpstreamError
from runtime.kit.text import JsonObject
from runtime.kit.time import epoch
from runtime.live.parts import LiveParts
from runtime.providers import service as providers
from runtime.providers.stage import Model, Running
from runtime.wire.flows import ExtractStep
from runtime.wire.metrics import LLMModelUsage
from runtime.wire.scores import ModelSpent

MODEL_SPENT = "model.spent"
TOOL = "extracted"
READ_IT = (
    "You read the text you are given and answer only by calling the tool {tool}, with what the text says. "
    "A field the text does not say is left out, never guessed, and nothing is added that the text does not hold."
)
ONLY_THE_TOOL = "Answer by calling {tool} with what the text says, and nothing else."
THE_TEXT = "the text a flow asked it to read"


@dataclass(frozen=True, slots=True)
class Extracting:
    """One extract step of a run: whose account, the words, the object's schema, what to look for, the model."""

    app: str
    flow: str
    run: str
    agent: str
    text: str
    shape: JsonObject
    instructions: str | None = None
    # vendor/model; None is the platform's own for a written turn, as the providers row says.
    model: str | None = None

    @classmethod
    def of(cls, app: str, flow: str, run: str, asked: ExtractStep) -> Self:
        """The step as its run's process sent it, for the run of the flow of the app."""
        return cls(app, flow, run, asked.agent, asked.text, asked.shape, asked.instructions, asked.model)


# One written turn, held to the org's messages as a chat's turn is, on the org's own key for the vendor
# or one the platform lends it (`lends`). The request is metered whether the model answered by the tool
# or not: it was asked, and it spent. The agent's own log is claimed for the org first, in a transaction
# of its own that commits before the spend is written: the log's writer appends on its own connection,
# and a claim left open in the step's transaction held it until the step gave up (found by the suite).
async def extract(session: AsyncSession, live: LiveParts, scope: Scope, asked: Extracting) -> JsonObject:
    """The object the model read from the words; UpstreamError when it would not answer by the schema."""
    async with live.sessions.begin() as own:
        owner = await calls.claim_agent_log(own, asked.agent, scope.org)
    if owner != scope.org:
        raise Conflict(f"the agent {asked.agent} is another org's: a flow extracts on its own org's agents")
    await billing.admit_turn(session, scope.org, scope.env, turns=1, tokens=0, at=epoch())
    catalog = await providers.get_catalog(session)
    keys = await providers.keys_of(session, live.vault, scope)
    running = providers.stage_on_its_key(Stage.llm, _read_model(asked.model), catalog, keys)
    tool = {"name": TOOL, "description": asked.instructions or "What the text says.", "parameters": asked.shape}
    lines = [providers.Line("system", _system(asked.instructions)), providers.Line("user", asked.text)]
    async with providers.open_answerer(running) as model:
        answer = await model.ask_by_tool(lines, tool, insist=ONLY_THE_TOOL.format(tool=TOOL), what=THE_TEXT)
    usage = [] if answer.usage is None else [_name_as_run(answer.usage, running)]
    spent = ModelSpent(
        app=asked.app,
        flow=asked.flow,
        run=asked.run,
        env=scope.env,
        turns=1,
        usage=usage,
        cost=providers.cost_of(usage, catalog),
        own_key=not running.lent,
    )
    await live.logs.agent(asked.agent).append(MODEL_SPENT, spent.dump())
    if answer.arguments is None:
        raise UpstreamError(f"the model answered without calling {TOOL}: it said {answer.text.strip()[:200]!r}")
    return dict(answer.arguments)


def _system(instructions: str | None) -> str:
    said = READ_IT.format(tool=TOOL)
    return said if instructions is None else f"{said}\n\n{instructions}"


def _read_model(model: str | None) -> Model | None:
    if model is None:
        return None
    vendor, _, name = model.partition("/")
    return Model(vendor=vendor, model=name)


# Priced by the names the operator configured, which the rates are keyed by, as a judge's spend is.
def _name_as_run(usage: LLMModelUsage, running: Running) -> LLMModelUsage:
    return usage.model_copy(update={"provider": running.vendor, "model": running.model or usage.model})
