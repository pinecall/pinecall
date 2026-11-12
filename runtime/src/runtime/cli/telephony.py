"""`fence`, `sip`: the networks 5060 opens to, and where the carriers send each env's calls."""

from typing import Annotated

import typer

from runtime import builders
from runtime.cli.command import OK, context_of, verb
from runtime.enums import Env
from runtime.exceptions import ValidationError
from runtime.scoping import box_wide
from runtime.telephony.service import fence, outbound

fence_app = typer.Typer(help="the networks 5060 opens to", no_args_is_help=True)
sip_app = typer.Typer(help="where the carriers send each env's calls", no_args_is_help=True)

NOT_AN_ENV_NAME = "--from takes ENV=NAME, like production=box.example.com; {given!r} is not"


# The orgs' addresses: written to the operator's own repository (ops/terraform/<env>.fence.tfvars.json),
# which the plan requires, never to this one.
@fence_app.command("export")
@verb
async def fence_export(ctx: typer.Context) -> int:
    """Every network 5060 opens to, the carriers' first, as Terraform's `sip_sources`."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            found = await fence.list_openings(session)
    context.out.data({"sip_sources": fence.list_every_network(found)})
    return OK


@sip_app.command("repoint")
@verb
async def sip_repoint(
    ctx: typer.Context,
    former: Annotated[
        list[str] | None,
        typer.Option("--from", help="ENV=NAME: a name the env was reached at before, its trunks sent on too."),
    ] = None,
) -> int:
    """Every carrier trunk at an env's name sent on to its SIP name, once; each trunk a line."""
    context = context_of(ctx)
    before: dict[Env, list[str]] = {}
    for given in former or []:
        env, equals, name = given.partition("=")
        if not equals or env not in Env.__members__.values() or not name:
            raise ValidationError(NOT_AN_ENV_NAME.format(given=given))
        before.setdefault(Env(env), []).append(name)
    handles = await context.handles()
    names = builders.read_sip_names(context.settings)
    async with handles.sessions.begin() as session:
        with box_wide():
            moved = await outbound.repoint_trunks(session, handles.vault, handles.http, names, before)
    context.out.rows(
        moved,
        (
            ("account", lambda item: item.account),
            ("trunk", lambda item: item.trunk),
            ("env", lambda item: item.env),
            ("was", lambda item: item.was),
            ("now", lambda item: item.now),
        ),
    )
    context.out.line(f"{len(moved)} trunks sent on")
    return OK
