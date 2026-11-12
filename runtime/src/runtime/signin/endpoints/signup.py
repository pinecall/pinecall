"""Sign-up: the org made from a mailed code, or for somebody Google vouched for, by whoever the box lets in."""

from fastapi import APIRouter

from runtime.accounts.auth import MinPassword, TheKeyCache
from runtime.mail.auth import TheOutbox
from runtime.postgres import Session
from runtime.signin import schemas
from runtime.signin.auth import Client, TheLoginCodes, TheNewcomers, TheSignInAttempts, TheSignUps, TheTurnstile
from runtime.signin.service import signup

router = APIRouter()


@router.post("/v1/signup", status_code=202)
async def sign_up(
    body: schemas.SignUp,
    client: Client,
    shortest: MinPassword,
    sign_ups: TheSignUps,
    turnstile: TheTurnstile,
    attempts: TheSignInAttempts,
    outbox: TheOutbox,
    session: Session,
) -> schemas.CodeMailed:
    """Keep the sign-up and mail its six digits; every address is answered alike."""
    asking = signup.Asking(body.email, body.person, body.password, body.org, body.name, body.device, body.turnstile)
    mailed = await signup.begin(
        session,
        sign_ups,
        asking,
        client=client,
        shortest=shortest,
        turnstile=turnstile,
        attempts=attempts,
        outbox=outbox,
    )
    return schemas.CodeMailed.of(mailed)


@router.post("/v1/signup/verify", status_code=201)
async def verify_signup(
    body: schemas.VerifySignUp,
    client: Client,
    sign_ups: TheSignUps,
    login_codes: TheLoginCodes,
    attempts: TheSignInAttempts,
    cache: TheKeyCache,
    session: Session,
) -> schemas.OrgMade:
    """The mailed code back: the org made, its admin seated, their first key and a login code."""
    founded = await signup.verify(
        session, cache, sign_ups, login_codes, body.email, body.code, client=client, attempts=attempts
    )
    return schemas.OrgMade.of(founded)


@router.post("/v1/signup/resend", status_code=202)
async def resend_code(
    body: schemas.ResendCode,
    client: Client,
    sign_ups: TheSignUps,
    turnstile: TheTurnstile,
    attempts: TheSignInAttempts,
    outbox: TheOutbox,
    session: Session,
) -> schemas.Empty:
    """A new code for a sign-up still waiting; the same answer for any address."""
    await signup.resend(
        session,
        sign_ups,
        body.email,
        body.turnstile,
        client=client,
        turnstile=turnstile,
        attempts=attempts,
        outbox=outbox,
    )
    return schemas.Empty()


# ── somebody Google vouched for ──


@router.get("/v1/signup/google/{token}")
async def google_newcomer(token: str, sign_ups: TheSignUps, newcomers: TheNewcomers) -> schemas.GoogleNewcomer:
    """Whom Google vouched for, spending nothing: the page asks them only for a workspace."""
    return schemas.GoogleNewcomer.of(await signup.get_newcomer(sign_ups, newcomers, token))


@router.post("/v1/signup/google", status_code=201)
async def sign_up_with_google(
    body: schemas.GoogleSignUp,
    client: Client,
    sign_ups: TheSignUps,
    newcomers: TheNewcomers,
    login_codes: TheLoginCodes,
    attempts: TheSignInAttempts,
    cache: TheKeyCache,
    session: Session,
) -> schemas.OrgMade:
    """The workspace named: the org made, its admin the address Google vouched for, no password and no code."""
    naming = signup.Naming(body.token, body.org, body.name, body.device)
    founded = await signup.found_with_google(
        session, cache, sign_ups, newcomers, login_codes, naming, client=client, attempts=attempts
    )
    return schemas.OrgMade.of(founded)
