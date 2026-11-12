"""`init`, `kill`, `orgs`: the tenants made, listed, erased, an agent moved or let go; on the services themselves."""

from typing import Annotated

import typer

from runtime import builders
from runtime.accounts import schemas
from runtime.accounts.models import BOX_ORG
from runtime.accounts.service import invitations, orgs
from runtime.accounts.service import members as memberships
from runtime.accounts.service.key_cache import KeyCache
from runtime.cli.command import OK, Context, context_of, verb
from runtime.cli.orgs import limits, provider_keys
from runtime.cli.orgs import members as people
from runtime.compliance.service.reads import OPERATOR
from runtime.enums import Role
from runtime.live import schemas as live
from runtime.retention.service.erasure import Erasing, erase_unused_org
from runtime.scoping import box_wide

app = typer.Typer(help="the tenants", no_args_is_help=True)
app.add_typer(provider_keys.app, name="provider-key")
app.command("invite")(people.orgs_invite)
app.command("operator")(people.orgs_operator)
app.command("remove-member")(people.orgs_remove_member)
app.command("password")(people.orgs_password)
app.command("quota")(limits.orgs_quota)
app.command("lends")(limits.orgs_lends)
app.command("simulating")(limits.orgs_simulating)
app.command("dialling")(limits.orgs_dialling)
app.command("sso")(limits.orgs_sso)

THE_FIRST_ROLE = Role.admin
WHAT_TO_DO_NEXT = """
  Open the link above to set a password. Then, on the machine an agent is written on:

    pinecall login {url}
    pinecall new <project> --agent <name>
    pinecall start
"""


@verb
async def init(
    ctx: typer.Context,
    email: Annotated[str, typer.Option("--email")],
    person: Annotated[str, typer.Option("--person", help="The person's name.")],
    org: Annotated[str, typer.Option("--org", help="The org's slug.")] = BOX_ORG,
    name: Annotated[str | None, typer.Option("--name", help="What to call the org (default: the slug).")] = None,
    role: Annotated[Role, typer.Option("--role")] = THE_FIRST_ROLE,
) -> int:
    """The org made or found, its first person invited and made an operator, the link once."""
    return await initialize(context_of(ctx), org=org, name=name, email=email, person=person, role=role)


# `setup` runs this too, on the settings it wrote.
async def initialize(context: Context, *, org: str, name: str | None, email: str, person: str, role: Role) -> int:
    """The first org and person on a fresh box, and what to do next."""
    handles = await context.handles()
    cache = KeyCache(handles.sessions, handles.signal)
    async with handles.sessions.begin() as session:
        with box_wide():
            found = await orgs.find_org(session, org)
            if found is None:
                found = await orgs.create_org(session, org, name or org)
                context.out.line(f"{found.id}  {found.slug}  {found.name}")
            else:
                context.out.line(f"org {org} is already there")
            invitee = invitations.Invitee(email, person, role)
            handed = await invitations.invite_as_operator(
                session, found, invitee, outbox=context.outbox(), base=context.settings.base_url
            )
            await memberships.set_operator(session, cache, handed.member, on=True)
    invited = schemas.Invited.of(handed)
    context.out.line(f"{invited.member.id}  {invited.member.email}  {invited.member.role}  runs this box")
    if invited.link:
        context.out.line(f"  {invited.link}")
    context.out.line(WHAT_TO_DO_NEXT.format(url=context.settings.base_url))
    return OK


@app.command("list")
@verb
async def orgs_list(ctx: typer.Context) -> int:
    """Every org, oldest first."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            rows = [schemas.OrgRow.of(org) for org in await orgs.list_orgs(session)]
    context.out.rows(rows, (("id", lambda org: org.id), ("slug", lambda org: org.slug), ("name", lambda org: org.name)))
    return OK


@app.command("add")
@verb
async def orgs_add(ctx: typer.Context, slug: str, name: Annotated[str | None, typer.Option("--name")] = None) -> int:
    """A new org, born with what admission gives one."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        with box_wide():
            made = await orgs.create_org(session, slug, name or slug)
    context.out.line(f"{made.id}  {made.slug}  {made.name}")
    return OK


# The registry of which app holds which agent lives in the gateways' memory: a move asks a gateway,
# which refuses while somebody holds the agent.
@app.command("move")
@verb
async def orgs_move(ctx: typer.Context, agent: str, org: str) -> int:
    """An agent's logs and numbers moved into the org, refused while an app holds it (asks a gateway)."""
    context = context_of(ctx)
    body = live.MoveAgentRequest(agent=agent)
    moved = await (await context.ops()).read("PUT", f"/v1/ops/orgs/{org}/agents", live.AgentMoved, body=body)
    context.out.line(f"{moved.agent} -> {moved.org}: {moved.logs} logs, numbers {', '.join(moved.numbers) or '-'}")
    context.out.lines([f"  {number} stayed: the org already answers at it" for number in moved.stayed])
    return OK


# Which app holds which agent lives in the gateways' memory: a kill asks a gateway, which tells
# every socket that holds the agent, on every gateway. Nothing is erased; the apps keep the others.
@verb
async def kill(
    ctx: typer.Context,
    agent: str,
    org: Annotated[str, typer.Option("--org", help="The org's slug.")] = BOX_ORG,
) -> int:
    """The agent let go by every app of the org that holds it, in either env (asks a gateway)."""
    context = context_of(ctx)
    killed = await (await context.ops()).read("POST", f"/v1/ops/orgs/{org}/agents/{agent}/kill", live.KilledAgent)
    context.out.line(f"{killed.agent} killed in {', '.join(killed.envs)}: {', '.join(killed.apps)} let go of it")
    return OK


@app.command("rm")
@verb
async def orgs_rm(ctx: typer.Context, org: str) -> int:
    """The org erased whole, its calls and recordings too; refused while a key or route names it."""
    context = context_of(ctx)
    handles = await context.handles()
    *_, logs = builders.build_log_engine(handles, context.stack)
    erasing = Erasing(builders.build_recordings(context.settings, handles.http), logs)
    async with handles.sessions.begin() as session:
        with box_wide():
            erased = await erase_unused_org(session, erasing, org, by=OPERATOR)
    context.out.line(f"org {org} is gone: {erased.calls} calls erased")
    return OK
