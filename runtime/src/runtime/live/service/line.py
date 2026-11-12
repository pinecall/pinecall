"""An agent's line and a developer's phone: whose terminal a ring lands in, the phone that reaches their copy."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Actor, Scope
from runtime.agents import service as agents
from runtime.enums import Env
from runtime.exceptions import Conflict, Forbidden
from runtime.kit.text import parse_e164
from runtime.live.holders import Holders
from runtime.live.service.apps import Holder, holder_of
from runtime.telephony import service as telephony

NOT_IN_PRODUCTION = "production has one scope and the org holds it: there is nothing to route"
NOBODY_TO_ROUTE_TO = "a phone reaches a person's own scope, and this key names no person"
NOBODY = Holder(holder=None, name=None)


@dataclass(frozen=True, slots=True)
class RingTarget:
    """Whose terminal a ring at the agent lands in, and who else could take it."""

    agent: str
    env: Env
    held: bool
    holding: Holder | None
    yours: bool
    waiting: list[Holder]
    calling: list[str]


@dataclass(frozen=True, slots=True)
class TestNumber:
    """A production number and the agent it reaches."""

    number: str
    agent: str


@dataclass(frozen=True, slots=True)
class TestNumbers:
    """The person's own phone, the agent it reaches, the box's test line, and the production numbers it can dial."""

    calling: list[str]
    numbers: list[TestNumber]
    agent: str | None
    # The box's own sandbox number a call from the phone reaches that agent at; None on a box with none.
    test_line: str | None


async def line_of(session: AsyncSession, holders: Holders, scope: Scope, slug: str) -> RingTarget:
    """Who holds the agent's line, and who else could take it."""
    holder = holders.line_of(scope.env, slug)
    waiting = [item for item in holders.list_waiting_for_line(scope, slug) if item.scope.holder != holder]
    holding = None
    if holder is not None:
        holding = await holder_of(session, Scope(scope.org, scope.env, holder)) or NOBODY
    return RingTarget(
        agent=slug,
        env=scope.env,
        held=holder is not None,
        holding=holding,
        # In production every holder is the org's own: the line is never "yours" there.
        yours=holder is not None and holder == scope.holder and scope.env is Env.sandbox,
        waiting=[await holder_of(session, waiter.scope) or NOBODY for waiter in waiting],
        calling=holders.phones_of(scope.env, scope.holder) if scope.holder else [],
    )


async def take_line(session: AsyncSession, holders: Holders, scope: Scope, slug: str) -> RingTarget:
    """Take the agent's line for this scope."""
    holders.take_line(scope, slug)
    return await line_of(session, holders, scope, slug)


async def drop_line(session: AsyncSession, holders: Holders, scope: Scope, slug: str) -> RingTarget:
    """Let the line go, to the newest other scope that could take it."""
    holders.drop_line(scope, slug)
    return await line_of(session, holders, scope, slug)


# The phone is the row's, so a gateway starting again still knows it, and the holders', so every
# gateway knows it now; the two are written together.
async def put_phone(
    session: AsyncSession, holders: Holders, actor: Actor, number: str, agent: str | None
) -> TestNumbers:
    """This phone is the person's own: a call from it reaches their copy of the agent named, or of the one held."""
    holder = _get_person(actor)
    phone = parse_e164(number)
    if agent is not None and not await holders.is_known(actor.org, agent):
        raise agents.NoSuchAgent(agent)
    await accounts.set_test_phone(session, actor.org, holder, phone, agent)
    holders.route_phone(actor.env, phone, holder)
    return await list_test_numbers(session, actor)


async def forget_phones(session: AsyncSession, holders: Holders, actor: Actor) -> list[str]:
    """Stop sending this person's phones to their scope, and say which were forgotten."""
    holder = _get_person(actor)
    forgotten = await accounts.forget_test_phone(session, actor.org, holder)
    said = holders.forget_phones(actor.env, holder)
    return sorted({*said, *([forgotten] if forgotten else [])})


# A developer lacks the numbers scope in production: this shows production's numbers and agents.
async def list_test_numbers(session: AsyncSession, actor: Actor) -> TestNumbers:
    """The phone that is the person's, the box's test line, and the production numbers it can dial."""
    member = (await accounts.get_member(session, actor.org, _get_person(actor))).member
    routes = await telephony.list_phone_routes(session, Scope(actor.org, Env.production))
    return TestNumbers(
        calling=[member.test_phone] if member.test_phone else [],
        numbers=[TestNumber(number=route.number, agent=route.agent) for route in routes],
        agent=member.test_agent,
        test_line=await telephony.find_test_line(session),
    )


def _get_person(actor: Actor) -> str:
    if actor.env is not Env.sandbox:
        raise Conflict(NOT_IN_PRODUCTION)
    if actor.person is None:
        raise Forbidden(NOBODY_TO_ROUTE_TO)
    return actor.person.id
