"""The operator's endpoints over every org: the box it opens, the orgs, their people, their SSO, their keys."""

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Path

from pinecall_runtime import __version__
from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import BrandDep, KeyCacheDep, OutboxDep, PublicUrl, TheOperator
from pinecall_runtime.accounts.service import emails, keys, members, orgs, sso
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.kit.text import parse_email, parse_slug
from pinecall_runtime.postgres import Session, box_wide

router = APIRouter()

MemberId = Annotated[str, Path(alias="id")]
# The path says {id}, as the console spells it; `id` is a builtin, so the function says member.
A_MEMBER = "/v1/ops/orgs/{named}/members/{id}"
# Who an email says invited, when the operator did.
THE_OPERATOR = "The operator"
NO_SSO = "org {slug} signs in with no identity provider"


# The console opens its Box screens when this answers 200; anything else hides them.
@router.get("/v1/ops/whoami")
async def box_identity(actor: TheOperator, handles: TheHandles) -> schemas.BoxIdentity:
    """The box this key opens, and the person holding it."""
    person = actor.person
    return schemas.BoxIdentity(
        operator=True,
        version=__version__,
        domain=handles.settings.domain,
        name=None if person is None else person.name,
        org=None if person is None else person.org,
    )


@router.get("/v1/ops/orgs")
async def list_orgs(_actor: TheOperator, session: Session) -> list[schemas.OrgRow]:
    """Every org, oldest first."""
    with box_wide():
        return [schemas.OrgRow.of(org) for org in await orgs.list_orgs(session)]


@router.post("/v1/ops/orgs", status_code=201)
async def create_org(body: schemas.CreateOrg, _actor: TheOperator, session: Session) -> schemas.OrgRow:
    """A new org, its id minted here, born with what admission gives one."""
    slug = parse_slug(body.slug.strip())
    with box_wide():
        return schemas.OrgRow.of(await orgs.create_org(session, slug, body.name or slug))


# ── its people ──


@router.get("/v1/ops/orgs/{named}/members")
async def org_members(named: str, _actor: TheOperator, session: Session) -> schemas.OrgMembers:
    """The org's people, oldest first, and how many hold a seat."""
    with box_wide():
        org = await orgs.get_org(session, named)
        listed = await members.list_members(session, org.id)
        return schemas.OrgMembers(
            members=[schemas.MemberRow.of(member) for member in listed],
            seated=await members.seats_taken(session, org.id),
        )


# Takes no seat of the org's plan: this is how an org gets its first admin with sign-up shut. The
# token is answered this once; the email goes too when the box can mail.
@router.post("/v1/ops/orgs/{named}/members", status_code=201)
async def invite_member(
    named: str,
    body: schemas.InviteMember,
    _actor: TheOperator,
    base: PublicUrl,
    session: Session,
    outbox_: OutboxDep,
    brand: BrandDep,
) -> schemas.Invited:
    """Invite a person into the org, the link's token once."""
    with box_wide():
        org = await orgs.get_org(session, named)
        invitee = members.Invitee(
            parse_email(body.email), body.name, body.role, frozenset(body.agents), body.production
        )
        link = await members.invite(session, org.id, invitee, seats=None, vouched=True)
    card = emails.card_link(base, link.token)
    details = emails.LinkDetails(org=org.name, link=card, by=THE_OPERATOR, dies=link.expires_at)
    mailed = await outbox_.post(None, emails.invitation_email(link.member.email, details, brand))
    return schemas.Invited(
        member=schemas.MemberRow.of(link.member), token=link.token, expires_at=link.expires_at, mailed=mailed, link=card
    )


# Here and not on the tenant's endpoint: an org admin could otherwise make itself the operator.
@router.put(f"{A_MEMBER}/operator")
async def set_operator(
    named: str,
    member: MemberId,
    body: schemas.OperatorChange,
    _actor: TheOperator,
    session: Session,
    cache: KeyCacheDep,
) -> schemas.MemberRow:
    """Whether this member runs the box; false takes it back at once."""
    with box_wide():
        org = await orgs.get_org(session, named)
        changed = await members.set_operator(session, org.id, member, on=body.operator)
    cache.forget(subject=member)
    return schemas.MemberRow.of(changed)


# The tenant endpoint's rules less "not yourself": the last active admin still stays.
@router.delete(A_MEMBER, status_code=204)
async def remove_member(
    named: str, member: MemberId, _actor: TheOperator, session: Session, cache: KeyCacheDep
) -> None:
    """The person out of the org for good, their keys revoked."""
    with box_wide():
        org = await orgs.get_org(session, named)
        await members.remove_member(session, org.id, member)
    cache.forget(subject=member)


# ── its identity provider ──


@router.get("/v1/ops/orgs/{named}/sso")
async def org_sso(
    named: str, _actor: TheOperator, handles: TheHandles, base: PublicUrl, session: Session
) -> schemas.SsoRow:
    """Which provider the org signs in with, never its secret."""
    with box_wide():
        org = await orgs.get_org(session, named)
        return await _sso(session, handles.vault, org.id, base)


# The break-glass: a password opens the org again while its provider is down. Never the other way:
# requiring the provider is the org's own call.
@router.put("/v1/ops/orgs/{named}/sso/required")
async def sso_required(
    named: str, body: schemas.SsoRequired, _actor: TheOperator, handles: TheHandles, base: PublicUrl, session: Session
) -> schemas.SsoRow:
    """Whether a password may still open the org beside its provider."""
    with box_wide():
        org = await orgs.get_org(session, named)
        wired = await sso.get_provider(session, handles.vault, org.id)
        if wired is None:
            raise NotFound(NO_SSO.format(slug=org.slug))
        await sso.put_provider(session, handles.vault, replace(wired, required=body.required))
        return await _sso(session, handles.vault, org.id, base)


# ── its keys ──


@router.get("/v1/ops/orgs/{named}/keys")
async def org_keys(named: str, _actor: TheOperator, session: Session) -> list[schemas.KeyRow]:
    """Every key of the org, oldest first, the revoked ones named as revoked; never a key."""
    with box_wide():
        org = await orgs.get_org(session, named)
        names = {member.id: member.name for member in await members.list_members(session, org.id)}
        return [schemas.KeyRow.with_names(key, names) for key in await keys.list_keys(session, org.id)]


# The one answer that carries the key: only its fingerprint is kept.
@router.post("/v1/ops/orgs/{named}/keys")
async def issue_key(named: str, body: schemas.IssueOrgKey, _actor: TheOperator, session: Session) -> schemas.KeyIssued:
    """A key of the org in the env named, answered this once."""
    with box_wide():
        org = await orgs.get_org(session, named)
        issue = keys.Issue(
            org=org.id,
            env=body.env,
            scopes=keys.KEY_SCOPES if body.scopes is None else frozenset(body.scopes),
            label=body.label,
            subject=body.subject,
            name=body.name,
        )
        key, secret = await keys.issue_key(session, issue)
    return schemas.KeyIssued.minted(key, secret)


# A POST, not a DELETE: the row stays, so the entries that name the key still read.
@router.post("/v1/ops/keys/{fingerprint}/revoke")
async def revoke_key(fingerprint: str, _actor: TheOperator, session: Session, cache: KeyCacheDep) -> schemas.KeyRevoked:
    """One key stops opening anything from the next request on."""
    with box_wide():
        stopped = await keys.revoke_fingerprint(session, fingerprint)
    if not stopped:
        raise keys.NoSuchKey(fingerprint)
    for each in stopped:
        cache.forget(fingerprint_=each)
    return schemas.KeyRevoked(fingerprint=fingerprint, revoked=True)


async def _sso(session: Session, vault: Vault, org: str, base: str) -> schemas.SsoRow:
    provider = await sso.get_provider(session, vault, org)
    return sso.sso_row(provider, base, await sso.proofs_of(session, org))
