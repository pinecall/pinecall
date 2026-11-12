"""`box alerts`: the operator's URL, where every org's alerts are posted too, and every org's alerts kept."""

from typing import Annotated

import typer

from runtime.alerts.service import alerts, webhooks
from runtime.cli.command import OK, context_of, verb
from runtime.cli.terminal import read_secret_line
from runtime.exceptions import NotFound
from runtime.postgres import BoxSession
from runtime.scoping import box_wide

app = typer.Typer(help="the operator's URL, where every org's alerts are posted too", no_args_is_help=True)

REACHES = "every org's alerts reach the operator at {url} · {signed}"
A_SECRET = "the signing secret, from stdin"


@app.command("show")
@verb
async def box_alerts_show(ctx: typer.Context) -> int:
    """Where every org's alerts are posted for the operator, and whether the posts are signed."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            found = await webhooks.operator_webhook_of(session, context.vault)
    if found is None:
        raise NotFound(webhooks.THE_OPERATOR_HEARS_NOTHING)
    context.out.line(REACHES.format(url=found.url, signed="signed" if found.signed else "unsigned"))
    return OK


# The same post an org's own webhook gets, org and env in it; --secret reads the signing secret
# from stdin, since argv is what `ps` shows. The operator's own may be inside the box's network.
@app.command("set")
@verb
async def box_alerts_set(
    ctx: typer.Context, url: str, secret: Annotated[bool, typer.Option("--secret", help=A_SECRET)] = False
) -> int:
    """Post every org's alerts to this URL too, from the next alert on."""
    context = context_of(ctx)
    webhook = webhooks.Webhook(url=url, secret=read_secret_line() if secret else None, public=False)
    async with context.sessions.begin() as session:
        with box_wide():
            await webhooks.put_operator_webhook(session, context.vault, webhook)
    context.out.line(REACHES.format(url=webhook.url, signed="signed" if webhook.signed else "unsigned"))
    return OK


# Read off the database, every org's unless one is named: what the box's tenants were told.
@app.command("list")
@verb
async def box_alerts_list(
    ctx: typer.Context,
    org: Annotated[str | None, typer.Option(help="one org's, by id")] = None,
    limit: Annotated[int, typer.Option(min=1, max=alerts.MOST_READ)] = alerts.READ,
) -> int:
    """Every org's alerts kept, newest first: when, whose, which kind, and whether it was mailed."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            found = await alerts.list_every_orgs_alerts(BoxSession(session), org=org, limit=limit)
    if not found:
        context.out.line("no alert kept: none was raised, or none in the last 90 days")
        return OK
    for row in found:
        mailed = "mailed" if row.mailed else "not mailed"
        context.out.line(
            f"{row.at:%Y-%m-%d %H:%M}  {row.org}  {row.env.value}  {row.kind}  {row.subject or '—'}  {mailed}"
        )
    return OK


@app.command("rm")
@verb
async def box_alerts_rm(ctx: typer.Context) -> int:
    """Stop posting the orgs' alerts to the operator; each org's own webhook goes on."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        with box_wide():
            await webhooks.delete_operator_webhook(session)
    context.out.line("the operator hears no alert: each org's own webhook goes on")
    return OK
