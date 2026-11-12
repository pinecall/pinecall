"""The platform's dependencies: the box's brand, loaded, and what each owner says on `/metrics`."""

from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from runtime.platform.service import brand
from runtime.platform.service.metrics import Collector
from runtime.postgres import Session


async def load_brand(session: Session) -> brand.Brand:
    """The box's brand as it stands."""
    return await brand.get_brand(session)


TheBrand = Annotated[brand.Brand, Depends(load_brand)]


def collectors_of(connection: HTTPConnection) -> tuple[Collector, ...]:
    """What each owner of the process says of itself on `/metrics`, in the order the lifespan listed them."""
    collectors: tuple[Collector, ...] = connection.state.collectors
    return collectors


TheCollectors = Annotated[tuple[Collector, ...], Depends(collectors_of)]
