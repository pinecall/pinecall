"""Sign-up: the org made from a mailed code, or for somebody Google vouched for, by whoever the box lets in."""

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
    Conflict,
    NotFound,
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
NO_NEWCOMER = (
    "the sign-in with Google behind this page is over: it was used, or ten minutes went by — continue with Google again"
)


def the_slug_asked(org: str | None, name: str | None) -> str:
    """The org's slug: the one typed, else made of its name; the page never derives one."""
    if org is not None and org.strip():
        return parse_slug(org.strip())
    if name is not None and name.strip():
        return slug_of(name)
    raise ValidationError("an org has a name, or a slug: one of the two")


def org_made(founded: signin.Founded) -> schemas.OrgMade:
    """What a sign-up answers once its org is made: the admin's key, the org, the console's code."""
    issued = schemas.KeyIssued.minted(founded.signed_in.key, founded.signed_in.secret)
    return schemas.OrgMade(
        **issued.model_dump(),
        slug=founded.slug,
        member=schemas.MemberRow.of(founded.admin),
        code=founded.code,
        code_expires_at=founded.code_expires_at,
    )


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
    slug = the_slug_asked(body.org, body.name)
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
    return org_made(await signin.found_org(session, taken.founding(), sign_ins_.codes))


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


# ── somebody Google vouched for ──


@router.get("/v1/signup/google/{token}")
async def google_newcomer(token: str, _client: SignupClient, sign_ins_: SignInsDep) -> schemas.GoogleNewcomer:
    """Whom Google vouched for, spending nothing: the page asks them only for a workspace."""
    kept = await sign_ins_.newcomers.read_alive(token)
    if kept is None:
        raise NotFound(NO_NEWCOMER)
    return schemas.GoogleNewcomer(email=kept.value.email, person=kept.value.person)


@router.post("/v1/signup/google", status_code=201)
async def sign_up_with_google(
    body: schemas.GoogleSignUp, client: SignupClient, session: Session, sign_ins_: SignInsDep
) -> schemas.OrgMade:
    """The workspace named: the org made, its admin the address Google vouched for, no password and no code."""
    await sign_ins_.attempts.check(f"{client} signup/google", "sign-ups from here")
    kept = await sign_ins_.newcomers.read_alive(body.token)
    if kept is None:
        raise NotFound(NO_NEWCOMER)
    newcomer = kept.value
    slug = the_slug_asked(body.org, body.name)
    # Somebody let in elsewhere since Google's callback signs in; a slug taken keeps the page to pick another.
    if await members.memberships_of(session, newcomer.email):
        raise Conflict(f"{newcomer.email} has an account here already: continue with Google again to sign in")
    if await orgs.find_org(session, slug) is not None:
        raise orgs.SlugTaken(slug)
    if await sign_ins_.newcomers.spend(body.token) is None:
        raise NotFound(NO_NEWCOMER)
    founding = signin.Founding(
        newcomer.email, slug, newcomer.person, body.name, hashed=None, device=body.device, vouched=True
    )
    return org_made(await signin.found_org(session, founding, sign_ins_.codes))
