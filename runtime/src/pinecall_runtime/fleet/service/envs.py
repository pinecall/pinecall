"""The fleet each env's calls are dispatched to, as the operator named them in the box's settings."""

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import Env
from pinecall_runtime.fleet.schemas import Fleets
from pinecall_runtime.platform import service as platform

FLEETS = "fleets"


async def fleets(session: AsyncSession) -> Fleets:
    """The fleet each env's calls go to; the defaults where the operator named none."""
    value = await platform.get_setting(session, FLEETS)
    return Fleets() if value is None else Fleets.model_validate(value)


async def set_fleets(session: AsyncSession, named: Fleets) -> None:
    """Write the fleet of each env, whole; the next dispatch reads it."""
    await platform.put_setting(session, FLEETS, named.model_dump(mode="json"))


def fleet_of(named: Fleets, env: Env) -> str:
    """The fleet a call of the env is dispatched to."""
    return named.production if env is Env.production else named.sandbox


async def fleet_of_env(session: AsyncSession, env: Env) -> str:
    """The fleet a call of the env is dispatched to, read from the settings now."""
    return fleet_of(await fleets(session), env)


def env_of_fleet(named: Fleets, fleet: str) -> Env | None:
    """The env whose calls go to the fleet; None when no env's do."""
    if fleet == named.production:
        return Env.production
    return Env.sandbox if fleet == named.sandbox else None
