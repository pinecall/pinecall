"""The apps and the line: the sockets an org has open, stopping one, whose terminal a ring lands in."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from pinecall_runtime.accounts.service import members, orgs
from pinecall_runtime.agents import schemas
from pinecall_runtime.agents.auth import (
    AppKey,
    CallsKey,
    FleetKey,
    KnownAgent,
    TheOperator,
    known_agent,
    sees_every_scope,
)
from pinecall_runtime.agents.service.registry import AgentRegistry, named_holder
from pinecall_runtime.calls import service as calls
from pinecall_runtime.channels import service as channels
from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.exceptions import Conflict, Forbidden, NotFound, ValidationError
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.kit.auth import Actor, Scope
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.postgres import Session, box_wide
from pinecall_runtime.telephony import service as telephony

router = APIRouter()

NOT_IN_PRODUCTION = "production has one scope and the org holds it: there is nothing to route"
# Every holder's process is cut, so it is an admin's: a key that opens both team and app.
ONLY_AN_ADMIN = "killing an agent is an admin's: it cuts every holder's app, and this key does not open team and app"
HELD_BY_NOBODY = "no app holds {slug} in {env}: there is nothing to kill"
KILLED_BY = "{slug} was killed by {name}"
NOBODY_OF_THE_ORG_HOLDS = "no app of {org} holds {slug}: there is nothing to kill"
OPERATOR_KILLED = "{slug} was killed by this box's operator"
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


# Nothing is erased: its settings, calls and logs stay, and an app that declares it again holds it
# again. The apps keep their other agents.
@router.post("/v1/agents/{slug}/kill")
async def kill_agent(slug: KnownAgent, actor: AppKey, request: Request) -> schemas.KilledAgent:
    """Let go of the agent in every app that holds it in the env, whoever's; an admin's."""
    if not sees_every_scope(actor):
        raise Forbidden(ONLY_AN_ADMIN)
    why = KILLED_BY.format(slug=slug, name=actor.name)
    apps = await calls.kill_agent(_live(request), _registry(request), actor.org, actor.env, slug, why)
    if not apps:
        raise NotFound(HELD_BY_NOBODY.format(slug=slug, env=actor.env))
    return schemas.KilledAgent(agent=slug, envs=[actor.env], apps=apps)


# The operator's kill reaches both envs of the org: what an admin of it would do in each.
@router.post("/v1/ops/orgs/{named}/agents/{slug}/kill")
async def kill_agent_of_org(
    named: str, slug: str, _actor: TheOperator, request: Request, session: Session
) -> schemas.KilledAgent:
    """Let go of the agent in every app of the org that holds it, in either env."""
    with box_wide():
        org = await orgs.get_org(session, named)
    why = OPERATOR_KILLED.format(slug=slug)
    envs: list[Env] = []
    apps: list[str] = []
    for env in Env:
        killed = await calls.kill_agent(_live(request), _registry(request), org.id, env, slug, why)
        envs += [env] if killed else []
        apps += killed
    if not apps:
        raise NotFound(NOBODY_OF_THE_ORG_HOLDS.format(slug=slug, org=org.slug))
    return schemas.KilledAgent(agent=slug, envs=envs, apps=apps)


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


# The phone is the row's, so a gateway starting again still knows it, and the registry's, so every
# gateway knows it now; the two are written together.
@router.put("/v1/line/from")
async def put_developer_phone(
    body: schemas.DeveloperPhone, actor: AppKey, request: Request, session: Session
) -> schemas.TestNumbers:
    """This phone is the person's own: a call from it reaches their copy of the agent named, or of the one held."""
    holder = _person_of(actor)
    number = parse_e164(body.number)
    agent = None if body.agent is None else await known_agent(body.agent, request)
    await members.set_test_phone(session, actor.org, holder, number, agent)
    _registry(request).calls_from(actor.env, number, holder)
    return await _test_numbers(session, actor, holder)


@router.delete("/v1/line/from")
async def drop_developer_phones(actor: AppKey, request: Request, session: Session) -> dict[str, list[str]]:
    """Stop sending this person's phones to their scope, and say which were forgotten."""
    holder = _person_of(actor)
    forgotten = await members.forget_test_phone(session, actor.org, holder)
    said = _registry(request).forget_calls_from(actor.env, holder)
    return {"forgot": sorted({*said, *([forgotten] if forgotten else [])})}


# A developer lacks the numbers scope in production: this shows production's numbers and agents.
@router.get("/v1/line/numbers")
async def list_test_numbers(actor: AppKey, session: Session) -> schemas.TestNumbers:
    """The phone that is the person's, the box's test line, and the production numbers it can dial."""
    return await _test_numbers(session, actor, _person_of(actor))


# A developer's own phone dialling the production number reaches their sandbox copy, while they
# hold it, or the org's own copy when nobody of theirs does (an app the box hosts, a Studio agent);
# every other caller reaches production. Where the sandbox has a LiveKit of its own, the ring is
# dialled there over SIP, through the trunk the answer carries.
@router.get("/v1/agents/{slug}/rings-for")
async def rings_for(
    slug: str,
    _actor: FleetKey,
    request: Request,
    session: Session,
    org: Annotated[str, Query()],
    caller: Annotated[str, Query()],
) -> telephony.RingHandoff:
    """Where a production ring from this phone goes: a developer's scope and fleet, or nowhere."""
    # The agent is the org's the ring was for, never the fleet's key's own org.
    registry = _registry(request)
    if not await registry.is_known(org, slug):
        return telephony.RingHandoff()
    taking = registry.taking_a_ring(Scope(org, Env.sandbox), slug, caller)
    if taking is None or not await _a_members_phone(session, org, caller):
        return telephony.RingHandoff()
    return telephony.RingHandoff(
        holder=taking.scope.holder,
        fleet=await fleet.fleet_of_env(session, Env.sandbox),
        trunk=telephony.hand_over_trunk(handles_of(request), caller),
    )


# A ring at the box's test line is already in the sandbox: the worker that took it runs the call
# as the caller's org's, in whichever copy takes a ring from that phone.
@router.get("/v1/test-line/rings-for")
async def test_line_rings_for(
    _actor: FleetKey,
    request: Request,
    session: Session,
    number: Annotated[str, Query()],
    caller: Annotated[str, Query()],
) -> telephony.RingAtTestLine:
    """Whose sandbox agent a ring at the box's test line is for: the org, the agent and the copy, or nobody's."""
    if parse_e164(number) != await telephony.get_test_line(session):
        return telephony.RingAtTestLine()
    try:
        phone = parse_e164(caller)
    except ValidationError:
        # A withheld number is nobody's.
        return telephony.RingAtTestLine()
    member = await members.whose_test_phone(session, phone)
    if member is None:
        return telephony.RingAtTestLine()
    registry = _registry(request)
    scope = Scope(member.org, Env.sandbox)
    agent = member.test_agent or _the_one_held(registry, scope)
    if agent is None:
        return telephony.RingAtTestLine(org=member.org)
    taking = registry.taking_a_ring(scope, agent, caller)
    holder = None if taking is None else taking.scope.holder
    return telephony.RingAtTestLine(org=member.org, agent=agent, holder=holder)


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


async def _test_numbers(session: Session, actor: Actor, holder: str) -> schemas.TestNumbers:
    member = await members.get_member(session, actor.org, holder)
    routes = await channels.routes_of_org(session, actor.org, Env.production)
    return schemas.TestNumbers(
        calling=[member.test_phone] if member.test_phone else [],
        agent=member.test_agent,
        test_line=await telephony.get_test_line(session),
        numbers=[
            schemas.TestNumber(number=route.number, agent=route.agent)
            for route in routes
            if route.channel == Channel.phone
        ],
    )


# The phone a ring comes from is a member's of this org: another org's member saying a phone is
# theirs diverts nothing of this org's.
async def _a_members_phone(session: Session, org: str, caller: str) -> bool:
    member = await members.whose_test_phone(session, caller)
    return member is not None and member.org == org


# The agent a phone reaches when its person named none: the one the org holds, if it holds one.
def _the_one_held(registry: AgentRegistry, scope: Scope) -> str | None:
    slugs = {held.slug for held in registry.holding(scope, every_scope=True) if held.takes_unclaimed}
    return next(iter(slugs)) if len(slugs) == 1 else None


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
