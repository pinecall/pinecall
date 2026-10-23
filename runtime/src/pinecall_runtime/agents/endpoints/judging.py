"""The org's hang-up judging, on or off and on what model; and an agent moved into the org it belongs to."""

from fastapi import APIRouter

from pinecall_runtime.accounts.service import orgs
from pinecall_runtime.agents import schemas
from pinecall_runtime.agents.auth import CallsKey, TheOperator, TheRegistry, UsageKey
from pinecall_runtime.agents.declaration import Model
from pinecall_runtime.agents.service.tuning import model_from_wire
from pinecall_runtime.calls import service as calls
from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import (
    Conflict,
    Forbidden,
    NotFound,
    ServiceUnavailable,
    UpstreamError,
    ValidationError,
)
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.postgres import Session, box_wide
from pinecall_runtime.providers import service as providers

router = APIRouter()

IN_THE_ENV = "{env} judges its calls on this model, and it cannot run there: {refused}"
NOT_HELD = "agent {slug} is held right now: stop it, move it, and start it again"
NO_SUCH_AGENT = "no agent named {slug} has ever written a log here"


# Per org, not per env: an org's evals are counted across both.
@router.get("/v1/org/judging")
async def get_judging(actor: CallsKey, session: Session) -> schemas.JudgingSettings:
    """Whether hang-up judging is on, the model it runs on, and its ceiling per call."""
    return await _judging(session, actor.org)


# The model is tried on the org's keys in each env, since both judge their calls on it: one the org
# cannot key there, a plugin of its own on a lent key, or a model its vendor turns away, is refused
# naming the env; asked once for each key it would run on, in the words of the vendor's no.
@router.put("/v1/org/judging")
async def put_judging(
    body: schemas.JudgingRequest, actor: UsageKey, handles: TheHandles, session: Session
) -> schemas.JudgingSettings:
    """Hang-up judging on or off, and the model it runs on, from the next call."""
    model = model_from_wire(body.model, "llm")
    if model is not None:
        catalog = await providers.get_catalog(session)
        tried: list[providers.Running] = []
        for env in Env:
            keyring = await providers.keys_of(session, handles.vault, Scope(actor.org, env))
            try:
                stage = providers.stage_on_its_key("llm", model, catalog, keyring)
                if stage not in tried:
                    await providers.try_stage("llm", stage, what=f"the judge model {_named(model)}")
                    tried.append(stage)
            except (Forbidden, ServiceUnavailable, Conflict, ValidationError, UpstreamError) as refused:
                raise type(refused)(IN_THE_ENV.format(env=env.value, refused=refused)) from refused
    await orgs.set_judging(session, actor.org, on=body.on)
    await orgs.set_judge_model(session, actor.org, body.model)
    return await _judging(session, actor.org)


# The way back from an agent registered with the wrong org's key: its logs and its numbers move.
# The operator's, since an org able to pull a slug could take another org's agent.
@router.put("/v1/ops/orgs/{named}/agents")
async def move_agent(
    named: str, body: schemas.MoveAgentRequest, _actor: TheOperator, registry: TheRegistry, session: Session
) -> schemas.AgentMoved:
    """An agent's logs and numbers moved into this org; refused while somebody holds it."""
    if registry.declared(body.agent) is not None:
        raise Conflict(NOT_HELD.format(slug=body.agent))
    with box_wide():
        org = await orgs.get_org(session, named)
        moved = await calls.move_logs(session, body.agent, org.id)
        if moved == 0:
            raise NotFound(NO_SUCH_AGENT.format(slug=body.agent))
        numbers, stayed = await channels.move_routes_with_agent(session, body.agent, org.id)
    return schemas.AgentMoved(agent=body.agent, org=org.slug, logs=moved, numbers=numbers, stayed=stayed)


def _named(model: Model) -> str:
    return f"{model.provider}/{model.model}" if model.model else model.provider


async def _judging(session: Session, org: str) -> schemas.JudgingSettings:
    catalog = await providers.get_catalog(session)
    return schemas.JudgingSettings(
        on=await orgs.is_judged(session, org),
        ceiling_usd=providers.judge_ceiling(catalog),
        model=await orgs.judge_model_of(session, org),
    )
