"""A route with the kind of the carrier account it lives in: what the numbers screens and the SIP rules read."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.channels import service as channels
from pinecall_runtime.channels.models import Route
from pinecall_runtime.enums import Env
from pinecall_runtime.telephony.repository import RouteCarrierRepository


@dataclass(frozen=True, slots=True)
class RouteRecord:
    """A route with the kind of the account it lives in."""

    route: Route
    # None for a number no account of the org holds: bought by the box, hooked, typed, or an
    # account since forgotten.
    carrier: str | None

    @property
    def last_call_at(self) -> float | None:
        """When a call to the number last reached the box, as an epoch; None when none ever did."""
        return None if self.route.last_call_at is None else self.route.last_call_at.timestamp()


async def record_of(session: AsyncSession, org: str, number: str) -> RouteRecord | None:
    """The org's route at this number with the kind of the account it lives in."""
    route = await channels.get_route(session, org, number)
    return None if route is None else RouteRecord(route, await RouteCarrierRepository(session).carrier_kind_of(route))


async def records_of(session: AsyncSession, org: str, env: Env) -> list[RouteRecord]:
    """The org's routes in one env, oldest first, each with its account's kind."""
    kinds = RouteCarrierRepository(session)
    return [
        RouteRecord(route, await kinds.carrier_kind_of(route))
        for route in await channels.routes_of_org(session, org, env)
    ]


async def phone_records_of(session: AsyncSession, org: str) -> list[RouteRecord]:
    """The org's phone numbers in both envs, oldest first, each with its account's kind."""
    kinds = RouteCarrierRepository(session)
    return [
        RouteRecord(route, await kinds.carrier_kind_of(route)) for route in await channels.phones_of_org(session, org)
    ]


async def records_on_the_box(session: AsyncSession) -> list[RouteRecord]:
    """Every route of every org and env, by number, with its account's kind."""
    return [
        RouteRecord(route, None if kind is None else str(kind))
        for route, kind in await RouteCarrierRepository(session).on_the_box()
    ]
