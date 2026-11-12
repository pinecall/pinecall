"""`providers`: the vendors this build runs, and the providers row: seeded once, its prices and models applied."""

from pathlib import Path
from typing import Annotated

import typer

from runtime.cli.command import OK, context_of, verb
from runtime.cli.output import Printer
from runtime.enums import Stage
from runtime.providers.catalog import Catalog
from runtime.providers.service import catalog as row
from runtime.providers.service import credentials, files, plugins, signatures
from runtime.providers.service.plugins import Vendor
from runtime.scoping import box_wide

app = typer.Typer(help="the vendors this build runs, and the providers row", no_args_is_help=True)


@app.command("list")
@verb
async def providers_list(
    ctx: typer.Context,
    does: Annotated[Stage | None, typer.Option("--does", help="Only the vendors of one stage.")] = None,
) -> int:
    """Every vendor this build runs, what it does, and whether the box holds its key."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            with_a_key = frozenset(await credentials.box_credentials(session, context.vault))
    vendors = sorted(plugins.list_vendors().values(), key=lambda vendor: vendor.name)
    shown = [vendor for vendor in vendors if does is None or does in vendor.does]

    def state(vendor: Vendor) -> str:
        return "broken" if vendor.broken else ("ready" if vendor.name in with_a_key else "no key")

    context.out.rows(shown, (("vendor", lambda v: v.name), ("does", lambda v: sorted(v.does)), ("state", state)))
    context.out.line(f"{len(shown)} vendors")
    return OK


# No database: what this build can run, for a setup that has not brought the services up yet.
@app.command("installed")
@verb
async def providers_installed(ctx: typer.Context) -> int:
    """Every vendor this build runs, what it does, and whether its ears end the caller's turn themselves."""
    context = context_of(ctx)
    vendors = sorted(plugins.list_vendors().values(), key=lambda vendor: vendor.name)

    def ends_turns(vendor: Vendor) -> bool:
        return vendor.broken is None and Stage.stt in vendor.does and signatures.ends_turns(vendor.name)

    context.out.rows(
        vendors,
        (
            ("vendor", lambda vendor: vendor.name),
            ("does", lambda vendor: sorted(vendor.does)),
            ("ends turns", lambda vendor: "yes" if ends_turns(vendor) else "no"),
            ("state", lambda vendor: "broken" if vendor.broken else "ready"),
        ),
    )
    return OK


# Once: a box that has a row is edited from the console, and a second seed is refused.
@app.command("seed")
@verb
async def providers_seed(
    ctx: typer.Context, file: Annotated[Path, typer.Argument(help="A JSON file of the row.")]
) -> int:
    """Write the providers row a box starts from, off a JSON file."""
    context = context_of(ctx)
    seeded = Catalog.model_validate_json(file.read_text(encoding="utf-8"))
    async with context.sessions.begin() as session:
        with box_wide():
            await row.seed_catalog(session, seeded)
    context.out.line("the providers row is written: the console edits it from now on")
    return OK


# Shown by default: a file written by mistake replaces what the console set.
@app.command("prices")
@verb
async def providers_prices(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="A CSV: vendor,model,unit,usd,as_of,source.")],
    apply: Annotated[bool, typer.Option("--apply", help="Write them into the box's row.")] = False,
) -> int:
    """What a prices file changes in the box's rates, and with --apply, the rates written."""
    context = context_of(ctx)
    written = files.rates_from_csv(file.read_text(encoding="utf-8"))
    async with context.sessions.begin() as session:
        with box_wide():
            catalog = await row.get_catalog(session)
            change = files.change_of(catalog.rates, written)
            if apply:
                await row.put_catalog(session, catalog.model_copy(update={"rates": {**catalog.rates, **written}}))
    return _say_change(context.out, change, applied=apply)


# Shown by default, as prices is: a file written by mistake replaces what the console set.
@app.command("models")
@verb
async def providers_models(
    ctx: typer.Context,
    file: Annotated[
        Path,
        typer.Argument(help="A CSV: vendor,stage,model,name,as_of,source, and recommended (yes) after them or not."),
    ],
    apply: Annotated[bool, typer.Option("--apply", help="Write them into the box's row.")] = False,
) -> int:
    """What a models file changes in what the box offers of each vendor, and with --apply, the models written."""
    context = context_of(ctx)
    read = files.models_from_csv(file.read_text(encoding="utf-8"))
    async with context.sessions.begin() as session:
        with box_wide():
            catalog = await row.get_catalog(session)
            change = files.change_of(catalog.offered, read.offered)
            if apply:
                kept = {named: leads for named, leads in catalog.recommended.items() if named not in read.offered}
                written = {
                    "offered": {**catalog.offered, **read.offered},
                    "names": {**catalog.names, **read.names},
                    "recommended": {**kept, **read.recommended},
                }
                await row.put_catalog(session, catalog.model_copy(update=written))
    return _say_change(context.out, change, applied=apply)


def _say_change(out: Printer, change: files.Change, *, applied: bool) -> int:
    if out.as_json:
        out.data({"change": change, "written": applied})
        return OK
    for mark, named in (("+", change.added), ("~", change.changed)):
        out.lines([f"{mark} {one}" for one in named])
    out.line(
        f"{len(change.added)} new, {len(change.changed)} changed, {len(change.unchanged)} the same, "
        f"{len(change.only_on_the_box)} only on the box and kept"
    )
    out.line("written" if applied else "nothing written: --apply writes them")
    return OK
