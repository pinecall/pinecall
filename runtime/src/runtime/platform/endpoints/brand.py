"""The box's brand, read and changed by its operator."""

from fastapi import APIRouter

from runtime.auth import TheOperator
from runtime.platform import schemas
from runtime.platform.auth import TheBrand
from runtime.platform.service import brand
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/ops/brand")
async def get_brand(_actor: TheOperator, kept: TheBrand) -> schemas.BrandRow:
    """What the box's emails and sign-in page are called and painted with."""
    return schemas.BrandRow.of(kept)


@router.put("/v1/ops/brand")
async def put_brand(body: schemas.PutBrand, _actor: TheOperator, kept: TheBrand, session: Session) -> schemas.BrandRow:
    """The brand changed field by field: one left out stays, an empty one goes to the default."""
    changed = brand.change_brand(kept, name=body.name, logo_url=body.logo_url, accent=body.accent)
    await brand.put_brand(session, changed)
    return schemas.BrandRow.of(changed)
