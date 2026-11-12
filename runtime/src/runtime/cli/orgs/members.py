"""`orgs invite|operator|remove-member|password`: an org's people, at the operator's word."""

import sys
from typing import Annotated

import typer

from runtime.accounts import schemas
from runtime.accounts.service import invitations, members, orgs
from runtime.accounts.service.key_cache import KeyCache
from runtime.cli.command import OK, context_of, verb
from runtime.cli.terminal import read_secret_line
from runtime.enums import Role
from runtime.scoping import box_wide

THE_FIRST_ROLE = Role.admin


# Takes no seat of the org's plan: this is how an org gets its first admin with sign-up shut.
@verb
async def orgs_invite(
    ctx: typer.Context,
    org: str,
    email: str,
    name: Annotated[str, typer.Option("--name")],
    role: Annotated[Role, typer.Option("--role")] = THE_FIRST_ROLE,
) -> int:
    """A person invited into an org, the link printed once."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            invitee = invitations.Invitee(email, name, role)
            handed = await invitations.invite_as_operator(
                session, found, invitee, outbox=context.outbox(), base=context.settings.base_url
            )
    invited = schemas.Invited.of(handed)
    member = invited.member
    context.out.line(f"{member.id}  {member.email}  {member.role}  {member.status}")
    if invited.link:
        context.out.line(f"  {invited.link}")
    elif not invited.mailed:
        context.out.warn("  the email did not go and no link is held: invite them again once the box can mail")
    return OK


# Here and not on the tenant's endpoint: an org admin could otherwise make itself the operator.
@verb
async def orgs_operator(
    ctx: typer.Context, org: str, email: str, revoke: Annotated[bool, typer.Option("--revoke")] = False
) -> int:
    """A member of the org made an operator of this box, or taken back at once."""
    context = context_of(ctx)
    handles = await context.handles()
    cache = KeyCache(handles.sessions, handles.signal)
    async with handles.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            member = await members.get_member_by_email(session, found.id, email)
            changed = schemas.MemberRow.of(await members.set_operator(session, cache, member, on=not revoke))
    runs = "runs this box" if changed.operator else "no longer runs this box"
    context.out.line(f"{changed.id}  {changed.email}  {runs}")
    return OK


@verb
async def orgs_remove_member(ctx: typer.Context, org: str, email: str) -> int:
    """A person out of the org for good, their keys revoked; the last active admin stays."""
    context = context_of(ctx)
    handles = await context.handles()
    cache = KeyCache(handles.sessions, handles.signal)
    async with handles.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            member = await members.get_member_by_email(session, found.id, email)
            await members.remove_member(session, cache, member)
    context.out.line(f"{email} is out of {org}")
    return OK


# A password is never an argument: argv is what `ps` shows and what a shell keeps.
@verb
async def orgs_password(ctx: typer.Context, org: str, email: str) -> int:
    """A person's password, asked twice at a terminal or read from stdin; an invited person becomes active."""
    context = context_of(ctx)
    password = new_password(sys.stdin.isatty())
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            member = await members.get_member_by_email(session, found.id, email)
            await members.set_password(session, member, password, context.settings.min_password)
    context.out.line(f"{email} signs in to {org} with the password typed, from the next sign-in")
    return OK


def new_password(asking: bool) -> str:
    """A password typed twice without echo at a terminal, else one line of stdin."""
    if asking:
        typed: str = typer.prompt("password", hide_input=True, confirmation_prompt=True)
        return typed
    return read_secret_line()
