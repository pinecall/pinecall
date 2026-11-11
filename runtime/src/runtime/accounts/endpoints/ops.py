"""The operator's endpoints over every org: the box a key opens, the orgs, their people, their keys."""

from importlib.metadata import version

from fastapi import APIRouter

from runtime.accounts import schemas
from runtime.accounts.auth import PublicUrl, TheKeyCache, TheNamedOrg, TheNamedOrgsMember
from runtime.accounts.service import invitations, keys, members, orgs
from runtime.auth import TheOperator
from runtime.enums import KEY_SCOPES
from runtime.handles import TheSettings
from runtime.mail.auth import TheOutbox
from runtime.postgres import TheBoxSession

router = APIRouter()

A_MEMBER = "/v1/ops/orgs/{named}/members/{id}"
# The distribution keeps its name whatever the package is imported as.
VERSION = version("pinecall-runtime")


# The console opens its Box screens when this answers 200; anything else hides them.
@router.get("/v1/ops/whoami")
async def box_identity(actor: TheOperator, settings: TheSettings) -> schemas.BoxIdentity:
    """The box this key opens, and the person holding it."""
    person = actor.person
    return schemas.BoxIdentity(
        operator=True,
        version=VERSION,
        domain=settings.domain,
        name=None if person is None else person.name,
        org=None if person is None else person.org,
    )


@router.get("/v1/ops/orgs")
async def list_orgs(_actor: TheOperator, session: TheBoxSession) -> list[schemas.OrgRow]:
    """Every org, oldest first."""
    return [schemas.OrgRow.of(org) for org in await orgs.list_orgs(session)]


@router.post("/v1/ops/orgs", status_code=201)
async def create_org(body: schemas.CreateOrg, _actor: TheOperator, session: TheBoxSession) -> schemas.OrgRow:
    """A new org, its id minted here, born with what admission gives one."""
    return schemas.OrgRow.of(await orgs.create_org(session, body.slug, body.name or body.slug))


# ── its people ──


@router.get("/v1/ops/orgs/{named}/members")
async def org_members(org: TheNamedOrg, session: TheBoxSession) -> schemas.OrgMembers:
    """The org's people, oldest first, and how many hold a seat."""
    return schemas.OrgMembers.of(await members.team_of(session, org.id))


# Takes no seat of the org's plan: this is how an org gets its first admin with sign-up shut. The
# token is answered this once; the email goes too when the box can mail.
@router.post("/v1/ops/orgs/{named}/members", status_code=201)
async def invite_member(
    org: TheNamedOrg,
    body: schemas.InviteMember,
    base: PublicUrl,
    outbox: TheOutbox,
    session: TheBoxSession,
) -> schemas.Invited:
    """Invite a person into the org, the link's token once."""
    invitee = invitations.Invitee(body.email, body.name, body.role, frozenset(body.agents), body.production)
    handed = await invitations.invite_as_operator(session, org, invitee, outbox=outbox, base=base)
    return schemas.Invited.of(handed)


# Here and not on the tenant's endpoint: an org admin could otherwise make itself the operator.
@router.put(f"{A_MEMBER}/operator")
async def set_operator(
    member: TheNamedOrgsMember, body: schemas.OperatorChange, cache: TheKeyCache, session: TheBoxSession
) -> schemas.MemberRow:
    """Whether this member runs the box; false takes it back at once."""
    return schemas.MemberRow.of(await members.set_operator(session, cache, member, on=body.operator))


# The tenant endpoint's rules less "not yourself": the last active admin still stays.
@router.delete(A_MEMBER, status_code=204)
async def remove_member(member: TheNamedOrgsMember, cache: TheKeyCache, session: TheBoxSession) -> None:
    """The person out of the org for good, their keys revoked."""
    await members.remove_member(session, cache, member)


# ── its keys ──


@router.get("/v1/ops/orgs/{named}/keys")
async def org_keys(org: TheNamedOrg, session: TheBoxSession) -> list[schemas.KeyRow]:
    """Every key of the org, oldest first, the revoked ones named as revoked; never a key."""
    return [schemas.KeyRow.of(key) for key in await keys.list_keys(session, org.id)]


# The one answer that carries the key: only its fingerprint is kept.
@router.post("/v1/ops/orgs/{named}/keys")
async def issue_key(org: TheNamedOrg, body: schemas.IssueOrgKey, session: TheBoxSession) -> schemas.KeyIssued:
    """A key of the org in the env named, answered this once."""
    issue = keys.Issue(
        org=org.id,
        env=body.env,
        scopes=KEY_SCOPES if body.scopes is None else frozenset(body.scopes),
        label=body.label,
        subject=body.subject,
        name=body.name,
    )
    return schemas.KeyIssued.of(await keys.issue_key(session, issue))


# A POST, not a DELETE: the row stays, so the entries that name the key still read.
@router.post("/v1/ops/keys/{fingerprint}/revoke")
async def revoke_key(
    fingerprint: str, _actor: TheOperator, cache: TheKeyCache, session: TheBoxSession
) -> schemas.KeyRevoked:
    """One key stops opening anything from the next request on."""
    await keys.revoke_as_operator(session, cache, fingerprint)
    return schemas.KeyRevoked(fingerprint=fingerprint, revoked=True)
