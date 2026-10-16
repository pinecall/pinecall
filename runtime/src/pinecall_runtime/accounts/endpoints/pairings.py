"""A terminal signed in by a browser: the code it prints, the browser's approval, the key it collects."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import (
    PairingsDep,
    PersonKey,
)
from pinecall_runtime.accounts.service import orgs, signin
from pinecall_runtime.exceptions import (
    Conflict,
    NotFound,
)
from pinecall_runtime.postgres import Session

router = APIRouter()

# Under the 30 s a proxy lets a quiet connection idle.
LONGEST_WAIT_S = 25.0
NO_PAIRING = "no pairing answers to that: it was collected, it expired, or it never existed"
ALREADY_ANSWERED = "that terminal is already signed in: it has a key waiting"


@router.post("/v1/login/pairings")
async def open_pairing(body: schemas.OpenPairing, pairings_: PairingsDep) -> schemas.CodeMinted:
    """The code a terminal prints for a browser to approve, and when it dies."""
    code, expires_at = await pairings_.open(body.device)
    return schemas.CodeMinted(code=code, expires_at=expires_at)


@router.get("/v1/login/pairings/{code}")
async def pairing_status(code: str, pairings_: PairingsDep) -> schemas.PairingStatus:
    """Which terminal a browser is about to sign in, and whether it is answered."""
    found = await pairings_.status(code)
    if found is None:
        raise NotFound(NO_PAIRING)
    waiting, expires_at = found
    return schemas.PairingStatus(device=waiting.device, expires_at=expires_at, answered=waiting.key is not None)


@router.post("/v1/login/pairings/{code}")
async def approve_pairing(
    code: str, actor: PersonKey, session: Session, pairings_: PairingsDep
) -> schemas.PairingApproved:
    """Sign the terminal in as the person this browser is; the terminal gets a key of its own."""
    found = await pairings_.status(code)
    if found is None:
        raise NotFound(NO_PAIRING)
    waiting, _ = found
    if waiting.key is not None:
        raise Conflict(ALREADY_ANSWERED)
    signed = await signin.another_device_key(session, actor, device=waiting.device)
    if not await pairings_.approve(code, signed.secret, signed.key.org):
        raise Conflict(ALREADY_ANSWERED)
    org = await orgs.find_org(session, signed.key.org)
    return schemas.PairingApproved(
        device=waiting.device, org=signed.key.org, org_name=signed.key.org if org is None else org.name
    )


@router.get("/v1/login/pairings/{code}/key")
async def collect_key(
    code: str,
    response: Response,
    pairings_: PairingsDep,
    wait_s: Annotated[float, Query(ge=0, le=LONGEST_WAIT_S)] = 0,
) -> schemas.KeyCollected | schemas.Empty:
    """The terminal's key, once; 202 while nobody has approved."""
    key, waiting = await pairings_.collect(code, within_s=wait_s)
    if key is not None:
        return schemas.KeyCollected(key=key)
    if not waiting:
        raise NotFound(NO_PAIRING)
    response.status_code = 202
    return schemas.Empty()
