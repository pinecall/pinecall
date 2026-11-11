"""The org's members: listed, invited, changed, removed, their password typed or reset."""

from fastapi import APIRouter

from runtime.accounts import schemas
from runtime.accounts.auth import MinPassword, PublicUrl, TeamKey, TheKeyCache, TheMember
from runtime.accounts.service import invitations, members
from runtime.mail.auth import TheOutbox
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/members")
async def list_members(actor: TeamKey, session: Session) -> schemas.MemberList:
    """Every member of the org, oldest first, the disabled ones too."""
    listed = await members.list_members(session, actor.org)
    return schemas.MemberList(members=[schemas.MemberRow.of(member) for member in listed])


@router.post("/v1/members", status_code=201)
async def invite_member(
    body: schemas.InviteMember, actor: TeamKey, base: PublicUrl, outbox: TheOutbox, session: Session
) -> schemas.Invited:
    """Invite a person, within the org's seats, and mail them the link."""
    invitee = invitations.Invitee(body.email, body.name, body.role, frozenset(body.agents), body.production)
    handed = await invitations.invite_as_admin(session, actor, invitee, outbox=outbox, base=base)
    return schemas.Invited.of(handed)


@router.patch("/v1/members/{id}")
async def change_member(
    member: TheMember, body: schemas.ChangeMember, actor: TeamKey, cache: TheKeyCache, session: Session
) -> schemas.MemberRow:
    """Change a member's role, agents, standing or production access; disabling revokes keys."""
    change = members.Change(
        role=body.role,
        agents=None if body.agents is None else frozenset(body.agents),
        status=body.status,
        production=body.production,
    )
    return schemas.MemberRow.of(await members.change_member(session, cache, actor, member, change))


@router.delete("/v1/members/{id}", status_code=204)
async def remove_member(member: TheMember, actor: TeamKey, cache: TheKeyCache, session: Session) -> None:
    """Take a member out for good, their keys revoked; never yourself, never the last admin."""
    await members.remove_colleague(session, cache, actor, member)


@router.put("/v1/members/{id}/password")
async def set_member_password(
    member: TheMember, body: schemas.SetPassword, actor: TeamKey, shortest: MinPassword, session: Session
) -> schemas.MemberRow:
    """A member's password set by an admin of the org, no link mailed; an invited member becomes active."""
    changed = await members.set_password_as_admin(session, actor, member, body.password, shortest)
    return schemas.MemberRow.of(changed)


@router.post("/v1/members/{id}/reset", status_code=201)
async def reset_password(
    member: TheMember, actor: TeamKey, base: PublicUrl, outbox: TheOutbox, session: Session
) -> schemas.Invited:
    """A one-time link that sets an active member's password, mailed to them."""
    handed = await invitations.reset_as_admin(session, actor, member, outbox=outbox, base=base)
    return schemas.Invited.of(handed)
