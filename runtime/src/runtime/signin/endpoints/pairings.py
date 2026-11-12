"""A terminal signed in by a browser: the code it prints, the browser's approval, the key it collects."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from runtime.accounts.auth import PersonKey
from runtime.postgres import Session
from runtime.signin import schemas
from runtime.signin.auth import ThePairings
from runtime.signin.service import pairings

router = APIRouter()

# Under the 30 s a proxy lets a quiet connection idle.
LONGEST_WAIT_S = 25.0
STILL_WAITING = 202


@router.post("/v1/login/pairings")
async def open_pairing(body: schemas.OpenPairing, terminals: ThePairings) -> schemas.CodeMinted:
    """The code a terminal prints for a browser to approve, and when it dies."""
    return schemas.CodeMinted.of(await terminals.open(body.device))


@router.get("/v1/login/pairings/{code}")
async def pairing_status(code: str, terminals: ThePairings) -> schemas.PairingStatus:
    """Which terminal a browser is about to sign in, and whether it is answered."""
    return schemas.PairingStatus.of(await terminals.get_status(code))


@router.post("/v1/login/pairings/{code}")
async def approve_pairing(
    code: str, actor: PersonKey, terminals: ThePairings, session: Session
) -> schemas.PairingApproved:
    """Sign the terminal in as the person this browser is; the terminal gets a key of its own."""
    return schemas.PairingApproved.of(await pairings.approve(session, terminals, code, actor))


@router.get("/v1/login/pairings/{code}/key")
async def collect_key(
    code: str,
    response: Response,
    terminals: ThePairings,
    wait_s: Annotated[float, Query(ge=0, le=LONGEST_WAIT_S)] = 0,
) -> schemas.KeyCollected | schemas.Empty:
    """The terminal's key, once; 202 while nobody has approved."""
    key = await terminals.collect(code, within_s=wait_s)
    if key is None:
        response.status_code = STILL_WAITING
        return schemas.Empty()
    return schemas.KeyCollected(key=key)
