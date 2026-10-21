"""Signing in: a password or a code for a key, the orgs a person opens, a code for a browser, a reset."""

from fastapi import APIRouter

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import (
    AnyKey,
    BrandDep,
    Client,
    OutboxDep,
    PersonKey,
    PublicUrl,
    SignInsDep,
    ThePerson,
    TurnstileDep,
)
from pinecall_runtime.accounts.service import keys, members, orgs, signin
from pinecall_runtime.enums import MemberStatus
from pinecall_runtime.exceptions import (
    NotFound,
    ValidationError,
)
from pinecall_runtime.postgres import Session, box_wide

router = APIRouter()

NO_CODE = "no code answers to that: it was used, it expired, or it never existed"
ONE_OR_THE_OTHER = "log in with org, email and password, or with a code: one of the two"


@router.post("/v1/login")
async def sign_in(
    body: schemas.SignIn, client: Client, session: Session, sign_ins_: SignInsDep, turnstile_: TurnstileDep
) -> schemas.KeyIssued:
    """A key for a person and a device, from a password, or from a one-time code."""
    if body.code is not None:
        if body.org is not None or body.email is not None or body.password is not None:
            raise ValidationError(ONE_OR_THE_OTHER)
        signed = await signin.sign_in_with_code(session, sign_ins_.codes, body.code, device=body.device)
        if signed is None:
            raise NotFound(NO_CODE)
        return schemas.KeyIssued.minted(signed.key, signed.secret)
    if body.email is None or body.password is None:
        raise ValidationError(ONE_OR_THE_OTHER)
    # A code is one use and minted by a signed-in page or a terminal; a password is what a stranger tries.
    await turnstile_.check(body.turnstile, "login", client)
    await sign_ins_.attempts.check(f"{client} {body.org or '*'}/{body.email}", body.email)
    asking = signin.PasswordSignIn(body.email, body.password, body.org, body.device)
    signed = await signin.sign_in_with_password(session, asking)
    return schemas.KeyIssued.minted(signed.key, signed.secret)


@router.post("/v1/login/orgs")
async def sign_in_orgs(
    body: schemas.SignInOrgs, client: Client, session: Session, sign_ins_: SignInsDep, turnstile_: TurnstileDep
) -> schemas.SignInOrgList:
    """The orgs an address and a password open, minting nothing."""
    await turnstile_.check(body.turnstile, "login", client)
    await sign_ins_.attempts.check(f"{client} */{body.email}", body.email)
    opened = await signin.orgs_a_password_opens(session, body.email, body.password)
    if not opened:
        raise signin.NobodyAnswers()
    rows: list[schemas.SignInOrgRow] = []
    for membership in opened:
        org = await orgs.find_org(session, membership.org)
        if org is not None:
            rows.append(schemas.SignInOrgRow(org=org.id, slug=org.slug, name=org.name, role=membership.role))
    return schemas.SignInOrgList(orgs=rows)


@router.get("/v1/login/orgs")
async def list_orgs_of_person(actor: PersonKey, person: ThePerson, session: Session) -> schemas.OrgsOfPerson:
    """Every org this key's person may open, oldest first, and which one this key opens."""
    rows: list[schemas.OrgOfPersonRow] = []
    with box_wide():
        for membership in await members.memberships_of(session, person.email):
            if membership.status is MemberStatus.disabled:
                continue
            org = await orgs.find_org(session, membership.org)
            rows.append(
                schemas.OrgOfPersonRow(
                    org=membership.org,
                    slug=None if org is None else org.slug,
                    name=None if org is None else org.name,
                    role=membership.role,
                    status=membership.status,
                    here=membership.org == actor.org,
                    member=True,
                )
            )
        if person.operator:
            theirs = {row.org for row in rows}
            for org in await orgs.list_orgs(session):
                if org.id not in theirs:
                    rows.append(
                        schemas.OrgOfPersonRow(
                            org=org.id,
                            slug=org.slug,
                            name=org.name,
                            role="operator",
                            status=MemberStatus.active,
                            here=org.id == actor.org,
                            member=False,
                        )
                    )
    return schemas.OrgsOfPerson(orgs=rows)


@router.post("/v1/login/org")
async def switch_org(
    body: schemas.SwitchOrg, actor: PersonKey, person: ThePerson, session: Session
) -> schemas.KeyIssued:
    """The same person's key in another org of theirs, or a visit for a person of the box."""
    with box_wide():
        org = await orgs.find_org(session, body.org)
    if org is None:
        raise signin.NotTheirOrg(body.org)
    signed = await signin.key_into_org(session, person, org.id, label=actor.label)
    return schemas.KeyIssued.minted(signed.key, signed.secret)


@router.post("/v1/login/codes")
async def mint_code(actor: AnyKey, session: Session, sign_ins_: SignInsDep) -> schemas.CodeMinted:
    """A one-time code that gives a browser a key like this one, for five minutes."""
    key = await keys.get_key(session, actor.key_id)
    code, expires_at = await sign_ins_.codes.mint(signin.holder_of_key(key))
    return schemas.CodeMinted(code=code, expires_at=expires_at)


@router.post("/v1/login/reset", status_code=202)
async def forget_password(
    body: schemas.ForgotPassword,
    client: Client,
    base: PublicUrl,
    session: Session,
    sign_ins_: SignInsDep,
    outbox_: OutboxDep,
    brand: BrandDep,
    turnstile_: TurnstileDep,
) -> schemas.Empty:
    """Mail a one-time link that sets the password, where one can go; 202 whoever asks."""
    await turnstile_.check(body.turnstile, "password_reset", client)
    await sign_ins_.attempts.check(f"{client} */{body.email}", body.email)
    await signin.mail_password_reset(session, outbox_, body.email, base, brand)
    return schemas.Empty()
