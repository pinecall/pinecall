"""Where an org's traces go: its collector read, kept and forgotten."""

from fastapi import APIRouter

from runtime.handles import TheVault
from runtime.postgres import Session
from runtime.providers import schemas
from runtime.providers.auth import ProvidersKey
from runtime.providers.service import telemetry

router = APIRouter()


@router.get("/v1/telemetry")
async def get_telemetry(actor: ProvidersKey, vault: TheVault, session: Session) -> schemas.TelemetryResponse | None:
    """The org's collector and which headers are set, never their values; null when none."""
    found = await telemetry.telemetry_of(session, vault, actor.org)
    return None if found is None else schemas.TelemetryResponse.of(found)


@router.put("/v1/telemetry", status_code=204)
async def put_telemetry(body: schemas.TelemetryRequest, actor: ProvidersKey, vault: TheVault, session: Session) -> None:
    """Keep the org's collector; its calls' traces go there from the next one."""
    wanted = telemetry.Telemetry(endpoint=body.endpoint, headers=body.headers, pii=body.pii)
    await telemetry.put_telemetry(session, vault, actor.org, wanted)


@router.delete("/v1/telemetry", status_code=204)
async def delete_telemetry(actor: ProvidersKey, session: Session) -> None:
    """Forget the org's collector; its calls' traces stay on the platform from the next one."""
    await telemetry.delete_telemetry(session, actor.org)
