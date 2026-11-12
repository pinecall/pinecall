"""Continue with Google: off to Google and back, and the operator keeping the box's client."""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from runtime.accounts.auth import PublicUrl, TheKeyCache
from runtime.auth import TheOperator
from runtime.handles import TheVault
from runtime.postgres import Session
from runtime.signin import schemas
from runtime.signin.auth import Client, TheLoginCodes, TheNewcomers, TheOidc, TheSignInAttempts, TheSignUps
from runtime.signin.service import google
from runtime.signin.service.oidc import Answer

router = APIRouter()

FOUND = 302


@router.get("/v1/login/google")
async def start_google(
    client: Client,
    base: PublicUrl,
    vault: TheVault,
    oidc: TheOidc,
    attempts: TheSignInAttempts,
    session: Session,
    pairing: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """302 to Google, with a state, a nonce and a PKCE challenge."""
    callback = f"{base}{schemas.GOOGLE_CALLBACK}"
    url = await google.begin(session, vault, oidc, attempts, client=client, redirect_uri=callback, pairing=pairing)
    return RedirectResponse(url, FOUND)


@router.get(schemas.GOOGLE_CALLBACK)
async def finish_google(
    state: str,
    cache: TheKeyCache,
    vault: TheVault,
    oidc: TheOidc,
    login_codes: TheLoginCodes,
    newcomers: TheNewcomers,
    sign_ups: TheSignUps,
    session: Session,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """The code exchanged; 302 to the console signed in, to the sign-up for a newcomer, or with why not."""
    answer = Answer(state, code, error)
    landing = await google.finish(
        session, cache, vault, oidc, login_codes, newcomers, answer, signups_open=sign_ups.accepting
    )
    return RedirectResponse(schemas.Landed.of(landing).location, FOUND)


# ── the operator's: Google, for every org's people ──


@router.get("/v1/ops/signin")
async def get_box_signin(_actor: TheOperator, base: PublicUrl, session: Session) -> schemas.BoxSignIn:
    """Every provider the box offers every org's people, and the URI each registers; never a secret."""
    wiring = await google.wiring_of(session, redirect_uri=f"{base}{schemas.GOOGLE_CALLBACK}")
    return schemas.BoxSignIn(google=schemas.BoxProvider.of(wiring))


@router.put("/v1/ops/signin/google")
async def put_google_signin(
    body: schemas.PutSignIn, _actor: TheOperator, base: PublicUrl, vault: TheVault, session: Session
) -> schemas.BoxProvider:
    """Keep the OAuth client the operator made at Google: "Continue with Google" shows on every page."""
    client = google.GoogleClient(client_id=body.client_id, client_secret=body.client_secret)
    callback = f"{base}{schemas.GOOGLE_CALLBACK}"
    return schemas.BoxProvider.of(await google.put_client(session, vault, client, redirect_uri=callback))


@router.delete("/v1/ops/signin/google", status_code=204)
async def delete_google_signin(_actor: TheOperator, session: Session) -> None:
    """Forget the client: the button goes from every page."""
    await google.delete_client(session)
