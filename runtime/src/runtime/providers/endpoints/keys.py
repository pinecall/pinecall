"""Vendor keys: the org's own, the box's, and an org's set for it by the operator; names only, never a key."""

from fastapi import APIRouter

from runtime.accounts.auth import TheNamedOrg
from runtime.auth import TheOperator
from runtime.handles import TheVault
from runtime.postgres import Session, TheBoxSession
from runtime.providers import schemas
from runtime.providers.auth import ProvidersKey
from runtime.providers.service import credentials, trials

router = APIRouter()


# ── an org's ──


# Vendor names only, never a key or a prefix of one.
@router.get("/v1/provider-keys")
async def list_own_vendors(actor: ProvidersKey, session: Session) -> schemas.VendorsResponse:
    """The vendors the org brought its own credentials for."""
    return schemas.VendorsResponse(vendors=await credentials.list_own_vendors(session, actor.org))


@router.put("/v1/provider-keys/{vendor}", status_code=204)
async def bring_key(
    vendor: str, body: schemas.ProviderKeyRequest, actor: ProvidersKey, vault: TheVault, session: Session
) -> None:
    """Keep the org's own credentials for a vendor; its calls run on them from the next one."""
    await trials.bring_key(session, vault, actor.org, vendor, body.key, body.credentials)


@router.delete("/v1/provider-keys/{vendor}", status_code=204)
async def take_key_back(vendor: str, actor: ProvidersKey, session: Session) -> None:
    """Forget the org's credentials for a vendor; its calls run on the box's from the next one."""
    await credentials.take_key_back(session, actor.org, vendor)


# ── the box's ──


# Offering a vendor is holding its key: the box's credentials, sealed, never read back.
@router.get("/v1/ops/provider-keys")
async def list_box_vendors(_actor: TheOperator, vault: TheVault, session: TheBoxSession) -> schemas.VendorsResponse:
    """The vendors the box holds a key for, never the key."""
    return schemas.VendorsResponse(vendors=await credentials.list_box_vendors(session, vault))


@router.put("/v1/ops/provider-keys/{vendor}", status_code=204)
async def put_box_key(
    vendor: str, body: schemas.ProviderKeyRequest, _actor: TheOperator, vault: TheVault, session: TheBoxSession
) -> None:
    """The box's own credentials for a vendor; orgs it lends to run on them from the next call."""
    await trials.bring_box_key(session, vault, vendor, body.key, body.credentials)


@router.delete("/v1/ops/provider-keys/{vendor}", status_code=204)
async def drop_box_key(vendor: str, _actor: TheOperator, vault: TheVault, session: TheBoxSession) -> None:
    """The box stops offering the vendor on its key; 404 when it held none."""
    await credentials.drop_box_key(session, vault, vendor)


# ── an org's vendor keys, set for it by the operator ──


@router.get("/v1/ops/orgs/{named}/provider-keys")
async def list_org_vendors(org: TheNamedOrg, session: TheBoxSession) -> schemas.VendorsResponse:
    """The vendors the org brought its own credentials for, never the credentials."""
    return schemas.VendorsResponse(vendors=await credentials.list_own_vendors(session, org.id))


@router.put("/v1/ops/orgs/{named}/provider-keys/{vendor}", status_code=204)
async def put_org_vendor_key(
    org: TheNamedOrg, vendor: str, body: schemas.ProviderKeyRequest, vault: TheVault, session: TheBoxSession
) -> None:
    """The org's own credentials for a vendor, set for it; its calls run on them next."""
    await trials.bring_key(session, vault, org.id, vendor, body.key, body.credentials)


@router.delete("/v1/ops/orgs/{named}/provider-keys/{vendor}", status_code=204)
async def drop_org_vendor_key(org: TheNamedOrg, vendor: str, session: TheBoxSession) -> None:
    """The org's credentials for a vendor taken back; its calls run on the box's next."""
    await credentials.take_key_back(session, org.id, vendor, whose=f"org {org.slug}")
