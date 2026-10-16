"""The apps and the line: the sockets an org has open, stopping one, whose terminal a ring lands in."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from pinecall_runtime.agents import schemas
from pinecall_runtime.agents.auth import AppKey, CallsKey, FleetKey, KnownAgent, sees_every_scope
from pinecall_runtime.agents.service.registry import AgentRegistry, named_holder
from pinecall_runtime.calls import service as calls
from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.exceptions import Conflict, Forbidden, NotFound
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.postgres import Session
from pinecall_runtime.telephony import service as telephony

router = APIRouter()

NOT_IN_PRODUCTION = "production has one scope and the org holds it: there is nothing to route"
NOBODY_TO_ROUTE_TO = "a phone reaches a person's own scope, and this key names no person"


@router.get("/v1/apps")
async def list_apps(actor: CallsKey, request: Request, session: Session) -> schemas.AppList:
    """The app sockets of the org in the env this key may see, oldest first."""
    registry = _registry(request)
    every = sees_every_scope(actor)
    listed: list[schemas.AppRow] = []
    for app in _live(request).apps_of(actor.org, actor.env):
        if not every and app.scope.holder not in ("", actor.holder):
            continue
        held = registry.owned_by(app.app)
        listed.append(
            schemas.AppRow(
                app=app.app,
                agents=[item.slug for item in held],
                env=app.scope.env,
                host=app.host,
                address=app.address,
                sdk=next((item.sdk for item in held if item.sdk is not None), None),
                holder=await named_holder(session, app.scope),
                connected_at=app.connected_at,
            )
        )
    return schemas.AppList(apps=listed)


# One 404 for every reason (another org, env or scope, gone): nothing leaks.
@router.post("/v1/apps/{app}/stop")
async def stop_app(app: str, actor: AppKey, request: Request) -> schemas.StopAppResponse:
    """Tell the app it was stopped, and close its socket, on whichever gateway holds it."""
    found = next((item for item in _live(request).apps_of(actor.org, actor.env) if item.app == app), None)
    if found is None or (not sees_every_scope(actor) and found.scope.holder not in ("", actor.holder)):
        raise NotFound(f"no app {app} is connected to this box that this key may stop")
    await found.stop(f"stopped by {actor.name}")
    return schemas.StopAppResponse(app=app, stopped=True)


# ── the line ──


@router.get("/v1/agents/{slug}/line")
async def get_line(slug: KnownAgent, actor: CallsKey, request: Request, session: Session) -> schemas.RingTarget:
    """Who holds the agent's line, and who else could take it."""
    return await _line(_registry(request), session, actor.scope, slug)


@router.post("/v1/agents/{slug}/line")
async def take_line(slug: KnownAgent, actor: AppKey, request: Request, session: Session) -> schemas.RingTarget:
    """Take the agent's line for this scope."""
    _registry(request).take_the_line(actor.scope, slug)
    return await _line(_registry(request), session, actor.scope, slug)


@router.delete("/v1/agents/{slug}/line")
async def drop_line(slug: KnownAgent, actor: AppKey, request: Request, session: Session) -> schemas.RingTarget:
    """Let the line go, to the newest other scope that could take it."""
    _registry(request).drop_the_line(actor.scope, slug)
    return await _line(_registry(request), session, actor.scope, slug)


@router.put("/v1/line/from")
async def put_developer_phone(body: schemas.DeveloperPhone, actor: AppKey, request: Request) -> dict[str, list[str]]:
    """Send rings from this phone to the key's person's own scope."""
    holder = _person_of(actor)
    _registry(request).calls_from(actor.env, parse_e164(body.number), holder)
    return {"calling": _registry(request).phones_of(actor.env, holder)}


@router.delete("/v1/line/from")
async def drop_developer_phones(actor: AppKey, request: Request) -> dict[str, list[str]]:
    """Stop sending this person's phones to their scope, and say which were forgotten."""
    return {"forgot": _registry(request).forget_calls_from(actor.env, _person_of(actor))}


# A developer lacks the numbers scope in production: this shows production's numbers and agents.
@router.get("/v1/line/numbers")
async def list_test_numbers(actor: AppKey, request: Request, session: Session) -> schemas.TestNumbers:
    """The production numbers a developer's phone can dial, and the phones that are theirs."""
    holder = _person_of(actor)
    routes = await channels.routes_of_org(session, actor.org, Env.production)
    return schemas.TestNumbers(
        calling=_registry(request).phones_of(actor.env, holder),
        numbers=[
            schemas.TestNumber(number=route.number, agent=route.agent)
            for route in routes
            if route.channel == Channel.phone
        ],
    )


# A developer's own phone dialling the production number reaches their sandbox copy, while they
# hold it; every other caller reaches production. Where the sandbox has a LiveKit of its own, the
# ring is dialled there over SIP, through the trunk the answer carries.
@router.get("/v1/agents/{slug}/rings-for")
async def rings_for(
    slug: KnownAgent,
    _actor: FleetKey,
    request: Request,
    session: Session,
    org: Annotated[str, Query()],
    caller: Annotated[str, Query()],
) -> telephony.RingHandoff:
    """Where a production ring from this phone goes: a developer's scope and fleet, or nowhere."""
    registry = _registry(request)
    taking = registry.taking_a_ring(Scope(org, Env.sandbox), slug, caller)
    if taking is None or not taking.scope.holder:
        return telephony.RingHandoff()
    if caller not in registry.phones_of(Env.sandbox, taking.scope.holder):
        return telephony.RingHandoff()
    return telephony.RingHandoff(
        holder=taking.scope.holder,
        fleet=await fleet.fleet_of_env(session, Env.sandbox),
        trunk=telephony.hand_over_trunk(handles_of(request), caller),
    )


# ── private ──


def _registry(request: Request) -> AgentRegistry:
    registry: AgentRegistry = request.app.state.registry
    return registry


# Every gateway's sockets: a stop reaches another gateway's through its inbox.
def _live(request: Request) -> calls.Live:
    serving: calls.Serving = request.app.state.serving
    return serving.live


def _person_of(actor: Actor) -> str:
    if actor.env is not Env.sandbox:
        raise Conflict(NOT_IN_PRODUCTION)
    if actor.person is None:
        raise Forbidden(NOBODY_TO_ROUTE_TO)
    return actor.person.id


async def _line(registry: AgentRegistry, session: Session, scope: Scope, slug: str) -> schemas.RingTarget:
    holder = registry.line_of(scope.env, slug)
    waiting = [item for item in registry.waiting_for_the_line(scope, slug) if item.scope.holder != holder]
    nobody = schemas.ScopeHolder(holder=None, name=None)
    holding = None
    if holder is not None:
        holding = await named_holder(session, Scope(scope.org, scope.env, holder)) or nobody
    return schemas.RingTarget(
        agent=slug,
        env=scope.env,
        held=holder is not None,
        holding=holding,
        # In production every holder is the org's own: the line is never "yours" there.
        yours=holder is not None and holder == scope.holder and scope.env is Env.sandbox,
        waiting=[await named_holder(session, waiter.scope) or nobody for waiter in waiting],
        calling=registry.phones_of(scope.env, scope.holder) if scope.holder else [],
    )
