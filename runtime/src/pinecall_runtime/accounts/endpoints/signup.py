"""Sign-up: the org made from a mailed code, by whoever the box lets in."""

from fastapi import APIRouter

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import (
    BrandDep,
    MinPassword,
    OutboxDep,
    SignInsDep,
    SignupClient,
    SignUpsDep,
    TurnstileDep,
)
from pinecall_runtime.accounts.service import emails, members, orgs, signin
from pinecall_runtime.exceptions import (
    ServiceUnavailable,
    ValidationError,
)
from pinecall_runtime.kit.text import parse_email, parse_slug, slug_of
from pinecall_runtime.postgres import Session

router = APIRouter()

REFUSED_SIGNUP: dict[signin.Refusal, str] = {
    "wrong": "that code is not valid",
    "expired": "that code has expired: ask for a new one",
    "burned": "too many tries: ask for a new code",
}


def the_slug_asked(body: schemas.SignUp) -> str:
    """The org's slug: the one typed, else made of its name; the page never derives one."""
    if body.org is not None and body.org.strip():
        return parse_slug(body.org.strip())
    if body.name is not None and body.name.strip():
        return slug_of(body.name)
    raise ValidationError("an org has a name, or a slug: one of the two")


@router.post("/v1/signup", status_code=202)
async def sign_up(
    body: schemas.SignUp,
    client: SignupClient,
    shortest: MinPassword,
    session: Session,
    sign_ins_: SignInsDep,
    sign_ups_: SignUpsDep,
    outbox_: OutboxDep,
    brand: BrandDep,
    turnstile_: TurnstileDep,
) -> schemas.CodeMailed:
    """Keep the sign-up and mail its six digits; every address is answered alike."""
    if await outbox_.mailbox_for(None) is None:
        raise ServiceUnavailable(
            "this box cannot mail a code: its operator sets PINECALL_SMTP_URL and PINECALL_MAIL_FROM"
        )
    await turnstile_.check(body.turnstile, "signup", client)
    await sign_ins_.attempts.check(f"{client} signup", "sign-ups from here")
    email = parse_email(body.email)
    slug = the_slug_asked(body)
    if not body.person.strip():
        raise ValidationError("a person has a name: it is what a seat says when they sit")
    hashed = await members.hashed_password(body.password, shortest)
    # Somebody who has a password signs up with it, or anybody could mint keys in their name; a
    # sign-up for an invited address would choose that person's password for them.
    known = await members.password_hash_of(session, email)
    notice = None
    if known is not None and not await members.password_matches(body.password, known):
        notice = emails.account_exists_email(email, brand)
    elif known is None and await members.memberships_of(session, email):
        notice = emails.invitation_waiting_email(email, brand)
    if notice is not None:
        await outbox_.post(None, notice)
        return schemas.CodeMailed(email=email, code_expires_at=sign_ins_.signups.clock() + signin.SIGNUP[1])
    if await orgs.find_org(session, slug) is not None:
        raise orgs.SlugTaken(slug)
    pending = signin.PendingSignUp(email, slug, body.person, hashed, "", "", body.name, body.device)
    code, expires_at = await sign_ups_.begin(pending)
    await outbox_.post(None, emails.signup_code_email(email, code, body.person, brand))
    return schemas.CodeMailed(email=email, code_expires_at=expires_at)


@router.post("/v1/signup/verify", status_code=201)
async def verify_signup(
    body: schemas.VerifySignUp, client: SignupClient, session: Session, sign_ins_: SignInsDep, sign_ups_: SignUpsDep
) -> schemas.OrgMade:
    """The mailed code back: the org made, its admin seated, their first key and a login code."""
    await sign_ins_.attempts.check(f"{client} signup/verify", "sign-ups from here")
    taken = await sign_ups_.verify(body.email.strip().lower(), body.code.strip())
    if isinstance(taken, str):
        raise ValidationError(REFUSED_SIGNUP[taken])
    founded = await signin.found_org(session, taken, sign_ins_.codes)
    issued = schemas.KeyIssued.minted(founded.signed_in.key, founded.signed_in.secret)
    return schemas.OrgMade(
        **issued.model_dump(),
        slug=founded.slug,
        member=schemas.MemberRow.of(founded.admin),
        code=founded.code,
        code_expires_at=founded.code_expires_at,
    )


@router.post("/v1/signup/resend", status_code=202)
async def resend_code(
    body: schemas.ResendCode,
    client: SignupClient,
    sign_ins_: SignInsDep,
    sign_ups_: SignUpsDep,
    outbox_: OutboxDep,
    brand: BrandDep,
    turnstile_: TurnstileDep,
) -> schemas.Empty:
    """A new code for a sign-up still waiting; the same answer for any address."""
    await turnstile_.check(body.turnstile, "signup_resend", client)
    await sign_ins_.attempts.check(f"{client} signup/resend", "sign-ups from here")
    renewed = await sign_ups_.renew(body.email.strip().lower())
    if renewed is not None:
        pending, code = renewed
        await outbox_.post(None, emails.signup_code_email(pending.email, code, pending.person, brand))
    return schemas.Empty()
