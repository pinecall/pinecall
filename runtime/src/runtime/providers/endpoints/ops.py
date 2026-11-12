"""The providers row, read and replaced whole by the box's operator."""

from fastapi import APIRouter

from runtime.auth import TheOperator
from runtime.postgres import TheBoxSession
from runtime.providers.catalog import Catalog
from runtime.providers.service import catalog

router = APIRouter()


@router.get("/v1/ops/providers")
async def get_providers(_actor: TheOperator, session: TheBoxSession) -> Catalog:
    """The providers row: defaults, models, voices, tuning, rates, the judge, the embedder."""
    return await catalog.get_catalog(session)


@router.put("/v1/ops/providers")
async def put_providers(body: Catalog, _actor: TheOperator, session: TheBoxSession) -> Catalog:
    """The providers row replaced whole; a vendor not installed or not doing its stage refused."""
    return await catalog.put_catalog(session, body)
