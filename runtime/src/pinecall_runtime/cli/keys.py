"""`keys`: an org's keys minted, listed and revoked, and an env's fleet and runner keys; on the database."""

from typing import Annotated

import typer

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.models import DEFAULT_ORG
from pinecall_runtime.accounts.service import keys, members, orgs
from pinecall_runtime.cli.command import OK, Context, context_of, verb
from pinecall_runtime.enums import Env, KeyScope

app = typer.Typer(help="keys: an org's, and the box's own for its fleets and runners", no_args_is_help=True)

A_FLEET_KEY = "the {env} fleet"
A_RUNNER_KEY = "the {env} runner"

Org = Annotated[str, typer.Option("--org", help="The org, by slug or id.")]


@app.command("issue")
@verb
async def keys_issue(
    ctx: typer.Context,
    env: Annotated[Env, typer.Option("--env", help="The env the key opens.")],
    org: Org = DEFAULT_ORG,
    label: Annotated[str | None, typer.Option("--label")] = None,
    scope: Annotated[list[KeyScope] | None, typer.Option("--scope", help="A scope; repeat for several.")] = None,
    subject: Annotated[str | None, typer.Option("--subject")] = None,
    name: Annotated[str | None, typer.Option("--name")] = None,
) -> int:
    """A key of an org in an env, printed once."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        found = await orgs.get_org(session, org)
        issue = keys.Issue(
            org=found.id,
            env=env,
            scopes=keys.KEY_SCOPES if not scope else frozenset(scope),
            label=label,
            subject=subject,
            name=name,
        )
        key, secret = await keys.issue_key(session, issue)
    minted = schemas.KeyIssued.minted(key, secret)
    if context.out.as_json:
        context.out.data(minted)
        return OK
    context.out.secret(minted.key)
    context.out.line(f"  org {found.slug} · {minted.env} · {minted.label or '-'}")
    context.out.line(f"  {', '.join(minted.scopes)}")
    context.out.line("  copy it now: the table keeps the fingerprint, and the key is never shown again")
    return OK


@app.command("list")
@verb
async def keys_list(ctx: typer.Context, org: Org = DEFAULT_ORG) -> int:
    """The org's keys by fingerprint, the revoked ones said; never a key."""
    context = context_of(ctx)
    async with context.sessions() as session:
        found = await orgs.get_org(session, org)
        names = {member.id: member.name for member in await members.list_members(session, found.id)}
        rows = [schemas.KeyRow.with_names(key, names) for key in await keys.list_keys(session, found.id)]
    context.out.rows(
        rows,
        (
            ("fingerprint", lambda key: key.fingerprint),
            ("env", lambda key: key.env or "person"),
            ("label", lambda key: key.label),
            ("state", lambda key: "revoked" if key.revoked_at else "live"),
            ("last used", lambda key: key.last_used_at),
        ),
    )
    return OK


# The row stays, so the entries that name the key still read; every gateway forgets it at once.
@app.command("revoke")
@verb
async def keys_revoke(ctx: typer.Context, fingerprint: str) -> int:
    """One key stopped from the next request on."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        stopped = await keys.revoke_fingerprint(session, fingerprint)
    if not stopped:
        raise keys.NoSuchKey(fingerprint)
    cache = keys.KeyCache(context.sessions, await context.signal())
    for each in stopped:
        cache.forget(fingerprint_=each)
    context.out.line(f"{fingerprint} opens nothing from now on")
    return OK


# Minted on the database, never over an endpoint: the box's own processes get theirs before any
# gateway answers. Printed to stdout once, where the job that mints it seals it.
@app.command("fleet")
@verb
async def keys_fleet(ctx: typer.Context, env: Env) -> int:
    """Mint an env's fleet key, in the box's own org, printed once."""
    return await _minted(context_of(ctx), env, KeyScope.fleet, A_FLEET_KEY.format(env=env))


# It is told every org's hosted apps and handed their tokens and secrets: minted like the fleet's.
@app.command("runner")
@verb
async def keys_runner(ctx: typer.Context, env: Env) -> int:
    """Mint an env's runner key, in the box's own org, printed once."""
    return await _minted(context_of(ctx), env, KeyScope.runner, A_RUNNER_KEY.format(env=env))


async def _minted(context: Context, env: Env, scope: KeyScope, label: str) -> int:
    issue = keys.Issue(org=DEFAULT_ORG, env=env, scopes=frozenset({scope}), label=label)
    async with context.sessions.begin() as session:
        _, secret = await keys.issue_key(session, issue)
    context.out.secret(secret)
    return OK
