"""The fleet each env's calls are dispatched to, as the operator named them in the box's settings."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Env
from runtime.platform import service as platform

PRODUCTION = "pinecall"
SANDBOX = "pinecall-sandbox"


@dataclass(frozen=True, slots=True)
class Fleets:
    """The fleet of workers each env's calls are dispatched to, as the operator named them."""

    production: str = PRODUCTION
    sandbox: str = SANDBOX


def _load(value: Mapping[str, Any]) -> Fleets:
    return Fleets(production=str(value.get("production") or PRODUCTION), sandbox=str(value.get("sandbox") or SANDBOX))


FLEETS: platform.Setting[Fleets] = platform.Setting("fleets", _load, asdict)


async def get_fleets(session: AsyncSession) -> Fleets:
    """The fleet each env's calls go to; the defaults where the operator named none."""
    return await platform.find_setting(session, FLEETS) or Fleets()


async def put_fleets(session: AsyncSession, named: Fleets) -> None:
    """Write the fleet of each env, whole; the next dispatch reads it."""
    await platform.put_setting(session, FLEETS, named)


def fleet_of(named: Fleets, env: Env) -> str:
    """The fleet a call of the env is dispatched to."""
    return named.production if env is Env.production else named.sandbox


async def fleet_of_env(session: AsyncSession, env: Env) -> str:
    """The fleet a call of the env is dispatched to, read from the settings now."""
    return fleet_of(await get_fleets(session), env)


def env_of_fleet(named: Fleets, fleet: str) -> Env | None:
    """The env whose calls go to the fleet; None when no env's do."""
    if fleet == named.production:
        return Env.production
    return Env.sandbox if fleet == named.sandbox else None
