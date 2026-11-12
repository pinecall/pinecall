"""`keys`: an org's keys minted, listed and revoked, and an env's runner key; on the database."""

from typing import Annotated

import typer

from runtime.accounts import schemas
from runtime.accounts.models import BOX_ORG
from runtime.accounts.service import keys, orgs
from runtime.accounts.service.key_cache import KeyCache
from runtime.cli.command import OK, context_of, verb
from runtime.enums import KEY_SCOPES, Env, KeyScope
from runtime.scoping import box_wide

app = typer.Typer(help="keys: an org's, and the box's own for its runners", no_args_is_help=True)

A_RUNNER_KEY = "the {env} runner"

Org = Annotated[str, typer.Option("--org", help="The org, by slug or id.")]


@app.command("issue")
@verb
async def keys_issue(
    ctx: typer.Context,
    env: Annotated[Env, typer.Option("--env", help="The env the key opens.")],
    org: Org = BOX_ORG,
    label: Annotated[str | None, typer.Option("--label")] = None,
    scope: Annotated[list[KeyScope] | None, typer.Option("--scope", help="A scope; repeat for several.")] = None,
    subject: Annotated[str | None, typer.Option("--subject")] = None,
    name: Annotated[str | None, typer.Option("--name")] = None,
) -> int:
    """A key of an org in an env, printed once."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            issue = keys.Issue(
                org=found.id,
                env=env,
                scopes=KEY_SCOPES if not scope else frozenset(scope),
                label=label,
                subject=subject,
                name=name,
            )
            minted = schemas.KeyIssued.of(await keys.issue_key(session, issue))
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
async def keys_list(ctx: typer.Context, org: Org = BOX_ORG) -> int:
    """The org's keys by fingerprint, the revoked ones said; never a key."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            found = await orgs.get_org(session, org)
            rows = [schemas.KeyRow.of(key) for key in await keys.list_keys(session, found.id)]
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
    handles = await context.handles()
    cache = KeyCache(handles.sessions, handles.signal)
    async with handles.sessions.begin() as session:
        with box_wide():
            await keys.revoke_as_operator(session, cache, fingerprint)
    context.out.line(f"{fingerprint} opens nothing from now on")
    return OK


# It is told every org's hosted apps and handed their tokens and secrets: minted on the database,
# never over an endpoint, and printed to stdout once, where the job that mints it seals it.
@app.command("runner")
@verb
async def keys_runner(ctx: typer.Context, env: Env) -> int:
    """Mint an env's runner key, in the box's own org, printed once."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        with box_wide():
            found = await orgs.get_org(session, BOX_ORG)
            label = A_RUNNER_KEY.format(env=env)
            issue = keys.Issue(org=found.id, env=env, scopes=frozenset({KeyScope.runner}), label=label)
            minted = await keys.issue_key(session, issue)
    context.out.secret(minted.key)
    return OK
