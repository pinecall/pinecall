"""The platform's dependencies: the box's brand, loaded."""

from typing import Annotated

from fastapi import Depends

from runtime.platform.service import brand
from runtime.postgres import Session


async def load_brand(session: Session) -> brand.Brand:
    """The box's brand as it stands."""
    return await brand.get_brand(session)


TheBrand = Annotated[brand.Brand, Depends(load_brand)]
