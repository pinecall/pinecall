"""`init`, `orgs`: the tenants, their people and their own vendor keys, on the services themselves."""

import sys
from typing import Annotated

import typer

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import emails, keys, members, orgs
from pinecall_runtime.agents import schemas as agents
from pinecall_runtime.calls import service as calls
from pinecall_runtime.cli.command import OK, Context, context_of, verb
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import Role
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.platform import service as platform
from pinecall_runtime.providers import service as providers
from pinecall_runtime.retention import service as retention

app = typer.Typer(help="the tenants", no_args_is_help=True)
vendor_keys_app = typer.Typer(help="the org's own vendor keys", no_args_is_help=True)
app.add_typer(vendor_keys_app, name="provider-key")

THE_FIRST_ROLE = Role.admin
# Who an email says invited, when the operator did from the terminal.
THE_OPERATOR = "The operator"
NOTHING_ON_STDIN = "the key is read from stdin, one line, and nothing came"
WHAT_TO_DO_NEXT = """
  Open the link above to set a password. Then, in the directory of an agent:

    pinecall login {url}
    pinecall link
    pinecall start
"""


@verb
async def init(
    ctx: typer.Context,
    email: Annotated[str, typer.Option("--email")],
    person: Annotated[str, typer.Option("--person", help="The person's name.")],
    org: Annotated[str, typer.Option("--org", help="The org's slug.")] = DEFAULT_ORG,
    name: Annotated[str | None, typer.Option("--name", help="What to call the org (default: the slug).")] = None,
    role: Annotated[Role, typer.Option("--role")] = THE_FIRST_ROLE,
) -> int:
    """The org made or found, its first person invited and made an operator, the link once."""
    return await initialize(context_of(ctx), org=org, name=name, email=email, person=person, role=role)


# `local init` runs this too, on the local settings.
async def initialize(context: Context, *, org: str, name: str | None, email: str, person: str, role: Role) -> int:
    """The first org and person on a fresh box, and what to do next."""
    async with context.sessions.begin() as session:
        found = await orgs.find_org(session, org)
        if found is None:
            found = await orgs.create_org(session, org, name or org)
            context.out.line(f"{found.id}  {found.slug}  {found.name}")
        else:
            context.out.line(f"org {org} is already there")
    invited = await _invite(context, found.id, email, person, role)
    async with context.sessions.begin() as session:
        await members.set_operator(session, found.id, invited.member.id, on=True)
    context.out.line(f"{invited.member.id}  {invited.member.email}  {invited.member.role}  runs this box")
    if invited.link:
        context.out.line(f"  {invited.link}")
    context.out.line(WHAT_TO_DO_NEXT.format(url=context.base_url))
    return OK


@app.command("list")
@verb
async def orgs_list(ctx: typer.Context) -> int:
    """Every org, oldest first."""
    context = context_of(ctx)
    async with context.sessions() as session:
        rows = [schemas.OrgRow.of(org) for org in await orgs.list_orgs(session)]
    context.out.rows(rows, (("id", lambda org: org.id), ("slug", lambda org: org.slug), ("name", lambda org: org.name)))
    return OK


@app.command("add")
@verb
async def orgs_add(ctx: typer.Context, slug: str, name: Annotated[str | None, typer.Option("--name")] = None) -> int:
    """A new org, born with what admission gives one."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        made = await orgs.create_org(session, slug, name or slug)
    context.out.line(f"{made.id}  {made.slug}  {made.name}")
    return OK


# Takes no seat of the org's plan: this is how an org gets its first admin with sign-up shut.
@app.command("invite")
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
    async with context.sessions() as session:
        found = await orgs.get_org(session, org)
    invited = await _invite(context, found.id, email, name, role)
    member = invited.member
    context.out.line(f"{member.id}  {member.email}  {member.role}  {member.status}")
    if invited.link:
        context.out.line(f"  {invited.link}")
    else:
        context.out.line("  already a person on this box: seated, they sign in with the password they have")
    return OK


# Here and not on the tenant's endpoint: an org admin could otherwise make itself the operator.
@app.command("operator")
@verb
async def orgs_operator(
    ctx: typer.Context, org: str, email: str, revoke: Annotated[bool, typer.Option("--revoke")] = False
) -> int:
    """A member of the org made an operator of this box, or taken back at once."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        member = await _member_by_email(context, found.id, email)
        changed = await members.set_operator(session, found.id, member.id, on=not revoke)
    await _forget_keys_of(context, member.id)
    runs = "runs this box" if changed.operator else "no longer runs this box"
    context.out.line(f"{changed.id}  {changed.email}  {runs}")
    return OK


@app.command("remove-member")
@verb
async def orgs_remove_member(ctx: typer.Context, org: str, email: str) -> int:
    """A person out of the org for good, their keys revoked; the last active admin stays."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        member = await _member_by_email(context, found.id, email)
        await members.remove_member(session, found.id, member.id)
    await _forget_keys_of(context, member.id)
    context.out.line(f"{member.email} is out of {org}")
    return OK


# The registry of which app holds which agent lives in the gateways' memory: a move asks a gateway,
# which refuses while somebody holds the agent.
@app.command("move")
@verb
async def orgs_move(ctx: typer.Context, agent: str, org: str) -> int:
    """An agent's logs and numbers moved into the org, refused while an app holds it (asks a gateway)."""
    context = context_of(ctx)
    body = agents.MoveAgentRequest(agent=agent)
    moved = await (await context.ops()).read("PUT", f"/v1/ops/orgs/{org}/agents", agents.AgentMoved, body=body)
    context.out.line(f"{moved.agent} -> {moved.org}: {moved.logs} logs, numbers {', '.join(moved.numbers) or '-'}")
    context.out.lines([f"  {number} stayed: the org already answers at it" for number in moved.stayed])
    return OK


@app.command("rm")
@verb
async def orgs_rm(ctx: typer.Context, org: str) -> int:
    """The org erased whole, its calls and recordings too; refused while a key or route names it."""
    context = context_of(ctx)
    recordings = calls.recordings_of(context.settings, await context.http())
    async with context.sessions.begin() as session:
        erased = await retention.erase_unused_org(session, recordings, org, by=compliance.OPERATOR)
    context.out.line(f"org {org} is gone: {len(erased.calls)} calls erased")
    return OK


# A password is never an argument: argv is what `ps` shows and what a shell keeps.
@app.command("password")
@verb
async def orgs_password(ctx: typer.Context, org: str, email: str) -> int:
    """A person's password, asked twice at a terminal or read from stdin; an invited person becomes active."""
    context = context_of(ctx)
    password = new_password(sys.stdin.isatty())
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        member = await members.member_by_email(session, found.id, email)
        await members.set_password(session, found.id, member.id, password, context.settings.min_password)
    context.out.line(f"{member.email} signs in to {org} with the password typed, from the next sign-in")
    return OK


def new_password(asking: bool) -> str:
    """A password typed twice without echo at a terminal, else one line of stdin."""
    if asking:
        typed: str = typer.prompt("password", hide_input=True, confirmation_prompt=True)
        return typed
    return read_secret_line()


# The key is read from stdin: argv is what `ps` shows.
@vendor_keys_app.command("set")
@verb
async def provider_key_set(ctx: typer.Context, org: str, vendor: str) -> int:
    """The org's own key for a vendor, read from stdin; its calls run on it from the next one."""
    context = context_of(ctx)
    named = providers.installed_vendor(vendor)
    credentials = read_secret_line()
    providers.check_credentials(named, credentials)
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        await providers.put_own_credentials(session, context.vault, found.id, named, credentials)
    context.out.line(f"{org} runs {named} on its own key from the next call")
    return OK


@vendor_keys_app.command("rm")
@verb
async def provider_key_rm(ctx: typer.Context, org: str, vendor: str) -> int:
    """The org's key for a vendor taken back; its calls run on the box's from the next one."""
    context = context_of(ctx)
    named = providers.installed_vendor(vendor)
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        if not await providers.drop_own_credentials(session, found.id, named):
            raise NotFound(f"org {found.slug} brought no key for {named}")
    context.out.line(f"{org} runs {named} on the box's key from the next call")
    return OK


@vendor_keys_app.command("list")
@verb
async def provider_key_list(ctx: typer.Context, org: str) -> int:
    """The vendors the org brought its own key for, never the key."""
    context = context_of(ctx)
    async with context.sessions() as session:
        found = await orgs.get_org(session, org)
        context.out.lines(await providers.own_vendors(session, found.id))
    return OK


def read_secret_line() -> str:
    """One line of stdin, a secret; refused when nothing came."""
    line = sys.stdin.readline().strip()
    if not line:
        raise ValidationError(NOTHING_ON_STDIN)
    return line


# The token is printed this once; the email goes too when the box can mail.
async def _invite(context: Context, org: str, email: str, name: str, role: Role) -> schemas.Invited:
    invitee = members.Invitee(email, name, role, frozenset(), False)
    async with context.sessions.begin() as session:
        link = await members.invite(session, org, invitee, seats=None, vouched=True)
        found = await orgs.get_org(session, org)
        brand = await platform.get_brand(session)
    card = emails.card_link(context.base_url, link.token)
    details = emails.LinkDetails(org=found.name, link=card, by=THE_OPERATOR, dies=link.expires_at)
    error = await (await context.outbox()).send(None, emails.invitation_email(link.member.email, details, brand))
    if error is not None:
        context.out.warn(f"  the email did not go ({error}): hand the link over yourself")
    return schemas.Invited(
        member=schemas.MemberRow.of(link.member),
        token=link.token,
        expires_at=link.expires_at,
        mailed=error is None,
        link=card,
    )


async def _member_by_email(context: Context, org: str, email: str) -> schemas.MemberRow:
    async with context.sessions() as session:
        listed = await members.list_members(session, org)
    wanted = email.strip().lower()
    for member in listed:
        if member.email.lower() == wanted:
            return schemas.MemberRow.of(member)
    raise NotFound(f"nobody in {org} has the address {email}")


# Every gateway forgets the person's keys it verified lately, so the change bites at once.
async def _forget_keys_of(context: Context, member: str) -> None:
    keys.KeyCache(context.sessions, await context.signal()).forget(subject=member)
