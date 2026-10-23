"""The compliance endpoints: the org's policy, who read its data, and where its traces go."""

from typing import Annotated

from fastapi import APIRouter, Query

from pinecall_runtime.compliance import schemas, service
from pinecall_runtime.compliance.auth import ProvidersKey, TeamKey
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.postgres import Session

router = APIRouter()


def _asked_by(actor: Actor) -> str:
    return actor.person.id if actor.person is not None else actor.key_id


# ── the policy ──


@router.get("/v1/org/policy")
async def get_policy(actor: TeamKey, session: Session) -> schemas.OrgPolicyRow:
    """The org's compliance settings: how long a sealed call is kept, calling rules, who set them."""
    return await service.policy_of(session, actor.org)


@router.put("/v1/org/policy")
async def put_policy(body: schemas.OrgPolicy, actor: TeamKey, session: Session) -> schemas.OrgPolicyRow:
    """Replace the org's compliance settings whole, from the next nightly run."""
    return await service.put_policy(session, actor.org, body, by=_asked_by(actor))


# ── who read what ──


@router.get("/v1/org/reads")
async def list_reads(
    actor: TeamKey, session: Session, subject: Annotated[str | None, Query()] = None
) -> schemas.ReadsResponse:
    """Who read the org's calls, recordings, exports and memory in the key's env; of one subject when named."""
    return schemas.ReadsResponse(reads=await service.list_reads(session, actor.scope, subject=subject))


# ── telemetry ──


@router.get("/v1/telemetry")
async def get_telemetry(actor: ProvidersKey, handles: TheHandles, session: Session) -> schemas.TelemetryResponse | None:
    """The org's collector and which headers are set, never their values; null when none."""
    return await service.describe_telemetry(session, handles.vault, actor.org)


@router.put("/v1/telemetry", status_code=204)
async def put_telemetry(
    body: schemas.TelemetryRequest, actor: ProvidersKey, handles: TheHandles, session: Session
) -> None:
    """Keep the org's collector; its calls' traces go there from the next one."""
    wanted = service.Telemetry(endpoint=body.endpoint, headers=body.headers, pii=body.pii)
    await service.put_telemetry(session, handles.vault, actor.org, wanted)


@router.delete("/v1/telemetry", status_code=204)
async def delete_telemetry(actor: ProvidersKey, session: Session) -> None:
    """Forget the org's collector; its calls' traces stay on the platform from the next one."""
    await service.drop_telemetry(session, actor.org)
