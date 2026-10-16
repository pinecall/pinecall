"""The org's members: listed, invited, changed, removed, their password reset."""

from typing import Annotated

from fastapi import APIRouter, Path

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import (
    BrandDep,
    KeyCacheDep,
    OutboxDep,
    PublicUrl,
    TeamKey,
)
from pinecall_runtime.accounts.service import emails, keys, members, orgs
from pinecall_runtime.accounts.service.mail import Outbox
from pinecall_runtime.billing import service as billing
from pinecall_runtime.enums import Env, MemberStatus, Role
from pinecall_runtime.exceptions import (
    Conflict,
    ValidationError,
)
from pinecall_runtime.kit.auth import Actor
from pinecall_runtime.kit.text import parse_email
from pinecall_runtime.platform import service as platform
from pinecall_runtime.postgres import Session

router = APIRouter()

MemberId = Annotated[str, Path(alias="id")]


@router.get("/v1/members")
async def list_members(actor: TeamKey, session: Session) -> schemas.MemberList:
    """Every member of the org, oldest first, the disabled ones too."""
    listed = await members.list_members(session, actor.org)
    return schemas.MemberList(members=[schemas.MemberRow.of(m) for m in listed])


@router.post("/v1/members", status_code=201)
async def invite_member(
    body: schemas.InviteMember, actor: TeamKey, base: PublicUrl, session: Session, outbox_: OutboxDep, brand: BrandDep
) -> schemas.Invited:
    """Invite a person, within the org's seats, and mail them the link."""
    email = parse_email(body.email)
    keys.check_may_grant(actor, body.role, production=body.production)
    elsewhere = await members.is_member_elsewhere(session, actor.org, email)
    seats = (await billing.get_quotas(session, actor.org, Env.production)).seats
    invitee = members.Invitee(email, body.name, body.role, frozenset(body.agents), body.production)
    link = await members.invite(session, actor.org, invitee, seats=seats, vouched=elsewhere)
    return await _invited(session, actor, base, link, emails.invitation_email, elsewhere, outbox_, brand)


@router.patch("/v1/members/{id}")
async def change_member(
    member: MemberId, body: schemas.ChangeMember, actor: TeamKey, session: Session, cache: KeyCacheDep
) -> schemas.MemberRow:
    """Change a member's role, agents, standing or production access; disabling revokes keys."""
    found = await members.get_member(session, actor.org, member)
    if body.status is MemberStatus.active and found.status is MemberStatus.invited:
        raise ValidationError(f"{found.email} has not accepted their invitation: they become active by accepting it")
    yours = actor.person is not None and actor.person.id == member
    if body.status is MemberStatus.disabled and yours:
        raise Conflict("you cannot disable yourself: another admin of this org disables you")
    if yours and (body.role is not None or body.production is not None):
        raise Conflict("nobody changes their own role or production access: another admin does")
    keys.check_may_grant(actor, body.role, production=bool(body.production))
    if body.production is False and (body.role or found.role) is Role.admin:
        raise Conflict(f"{found.email} is an admin, and an admin always opens production")
    change = members.Change(
        role=body.role,
        agents=None if body.agents is None else frozenset(body.agents),
        status=body.status,
        production=body.production,
    )
    changed = await members.update_member(session, actor.org, member, change)
    cache.forget(subject=member)
    return schemas.MemberRow.of(changed)


@router.delete("/v1/members/{id}", status_code=204)
async def remove_member(member: MemberId, actor: TeamKey, session: Session, cache: KeyCacheDep) -> None:
    """Take a member out for good, their keys revoked; never yourself, never the last admin."""
    if actor.person is not None and actor.person.id == member:
        raise Conflict("you cannot remove yourself: another admin of this org removes you")
    await members.remove_member(session, actor.org, member)
    cache.forget(subject=member)


@router.post("/v1/members/{id}/reset", status_code=201)
async def reset_password(
    member: MemberId, actor: TeamKey, base: PublicUrl, session: Session, outbox_: OutboxDep, brand: BrandDep
) -> schemas.Invited:
    """A one-time link that sets an active member's password, mailed to them."""
    found = await members.get_member(session, actor.org, member)
    elsewhere = await members.is_member_elsewhere(session, actor.org, found.email)
    link = await members.reset_link(session, actor.org, member, vouched=elsewhere)
    if link is None:
        raise Conflict(
            f"{found.email} is {found.status}, not active: an invited member uses their invitation, "
            "and a disabled one is enabled before their password is reset"
        )
    return await _invited(session, actor, base, link, emails.reset_email, elsewhere, outbox_, brand)


# The token is handed to the admin only when the address is in no other org; otherwise it is mailed
# only, by the box's own mailbox, and the link seats the person with the password they have.
async def _invited(
    session: Session,
    actor: Actor,
    base: str,
    link: members.Link,
    worded: emails.Worded,
    elsewhere: bool,
    outbox_: Outbox,
    brand: platform.Brand,
) -> schemas.Invited:
    org = await orgs.find_org(session, actor.org)
    details = emails.LinkDetails(
        org=actor.org if org is None else org.name,
        link=emails.card_link(base, link.token),
        by=actor.name or "An admin",
        dies=link.expires_at,
    )
    mailed = await outbox_.post(None if elsewhere else actor.org, worded(link.member.email, details, brand))
    return schemas.Invited(
        member=schemas.MemberRow.of(link.member),
        token=None if elsewhere else link.token,
        expires_at=link.expires_at,
        mailed=mailed,
        link=None if elsewhere else emails.card_link(base, link.token),
    )
