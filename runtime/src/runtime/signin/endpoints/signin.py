"""Signing in: a password or a code for a key, the orgs a person opens, a code for a browser, a reset."""

from fastapi import APIRouter

from runtime.accounts.auth import AnyKey, PersonKey, PublicUrl, ThePerson
from runtime.accounts.schemas import KeyIssued
from runtime.exceptions import ValidationError
from runtime.mail.auth import TheOutbox
from runtime.postgres import Session
from runtime.signin import schemas
from runtime.signin.auth import Client, TheLoginCodes, ThePasswordThrottle, TheSignInAttempts, TheTurnstile
from runtime.signin.service import codes, passwords

router = APIRouter()


# One route, two ways in, as every client of the box spells it: which one is read off the body.
@router.post("/v1/login")
async def sign_in(
    body: schemas.SignIn, client: Client, login_codes: TheLoginCodes, throttle: ThePasswordThrottle, session: Session
) -> KeyIssued:
    """A key for a person and a device, from a password, or from a one-time code."""
    if body.code is not None:
        if body.org is not None or body.email is not None or body.password is not None:
            raise ValidationError("log in with org, email and password, or with a code: one of the two")
        return KeyIssued.of(await codes.sign_in_with_code(session, login_codes, body.code, device=body.device))
    if body.email is None or body.password is None:
        raise ValidationError("log in with org, email and password, or with a code: one of the two")
    asking = passwords.PasswordSignIn(body.email, body.password, body.org, body.device)
    return KeyIssued.of(await passwords.sign_in_with_password(session, throttle, asking, client=client))


@router.post("/v1/login/orgs")
async def sign_in_orgs(
    body: schemas.SignInOrgs, client: Client, throttle: ThePasswordThrottle, session: Session
) -> schemas.SignInOrgList:
    """The orgs an address and a password open, minting nothing."""
    opened = await passwords.list_orgs_a_password_opens(session, throttle, body.email, body.password, client=client)
    return schemas.SignInOrgList(orgs=[schemas.SignInOrgRow.of(org) for org in opened])


@router.get("/v1/login/orgs")
async def list_orgs_of_person(actor: PersonKey, person: ThePerson, session: Session) -> schemas.OrgsOfPerson:
    """Every org this key's person may open, oldest first, and which one this key opens."""
    opened = await codes.list_orgs_of_person(session, person, actor.org)
    return schemas.OrgsOfPerson(orgs=[schemas.OrgOfPersonRow.of(org) for org in opened])


@router.post("/v1/login/org")
async def switch_org(body: schemas.SwitchOrg, actor: PersonKey, person: ThePerson, session: Session) -> KeyIssued:
    """The same person's key in another org of theirs, or a visit for a person of the box."""
    return KeyIssued.of(await codes.key_into_org(session, person, body.org, label=actor.label))


@router.post("/v1/login/codes")
async def mint_code(actor: AnyKey, login_codes: TheLoginCodes, session: Session) -> schemas.CodeMinted:
    """A one-time code that gives a browser a key like this one, for five minutes."""
    return schemas.CodeMinted.of(await codes.mint_for_key(session, login_codes, actor.key_id))


@router.post("/v1/login/reset", status_code=202)
async def forget_password(
    body: schemas.ForgotPassword,
    client: Client,
    base: PublicUrl,
    turnstile: TheTurnstile,
    attempts: TheSignInAttempts,
    outbox: TheOutbox,
    session: Session,
) -> schemas.Empty:
    """Mail a one-time link that sets the password, where one can go; 202 whoever asks."""
    await passwords.forget_password(
        session,
        body.email,
        body.turnstile,
        client=client,
        base=base,
        turnstile=turnstile,
        attempts=attempts,
        outbox=outbox,
    )
    return schemas.Empty()
