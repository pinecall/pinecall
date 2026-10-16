"""`providers`, `memory`, `vault`: the vendors this build runs and the row, the embedder's facts, the sealing key."""

from pathlib import Path
from typing import Annotated

import typer

from pinecall_runtime.cli.command import FOUND_WRONG, OK, context_of, verb
from pinecall_runtime.enums import Stage
from pinecall_runtime.exceptions import ServiceUnavailable
from pinecall_runtime.knowledge import service as knowledge
from pinecall_runtime.providers import service as providers
from pinecall_runtime.retention import service as retention

app = typer.Typer(help="the vendors this build runs, and the providers row", no_args_is_help=True)
memory_app = typer.Typer(help="contact memory", no_args_is_help=True)
vault_app = typer.Typer(help="the key every secret is sealed under", no_args_is_help=True)

NO_EMBEDDER = "this box embeds nothing: no embedding in its providers row"


@app.command("list")
@verb
async def providers_list(
    ctx: typer.Context,
    does: Annotated[Stage | None, typer.Option("--does", help="Only the vendors of one stage.")] = None,
) -> int:
    """Every vendor this build runs, what it does, and whether the box holds its key."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with_a_key = frozenset(await providers.box_credentials(session, context.vault))
    vendors = sorted(providers.installed().values(), key=lambda vendor: vendor.name)
    shown = [vendor for vendor in vendors if does is None or does.value in vendor.does]

    def state(vendor: providers.Vendor) -> str:
        return "broken" if vendor.broken else ("ready" if vendor.name in with_a_key else "no key")

    context.out.rows(shown, (("vendor", lambda v: v.name), ("does", lambda v: sorted(v.does)), ("state", state)))
    context.out.line(f"{len(shown)} vendors")
    return OK


# Once: a box that has a row is edited from the console, and a second seed is refused.
@app.command("seed")
@verb
async def providers_seed(
    ctx: typer.Context, file: Annotated[Path, typer.Argument(help="A JSON file of the row.")]
) -> int:
    """Write the providers row a box starts from, off a JSON file."""
    context = context_of(ctx)
    seeded = providers.Catalog.model_validate_json(file.read_text(encoding="utf-8"))
    async with context.sessions.begin() as session:
        await providers.seed_catalog(session, seeded)
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
    written = providers.rates_from_csv(file.read_text(encoding="utf-8"))
    async with context.sessions.begin() as session:
        catalog = await providers.get_catalog(session)
        change = providers.rates_changed(catalog.rates, written)
        if apply:
            await providers.put_catalog(session, catalog.model_copy(update={"rates": {**catalog.rates, **written}}))
    if context.out.as_json:
        context.out.data({"change": change, "written": apply})
        return OK
    for mark, models in (("+", change.added), ("~", change.changed)):
        context.out.lines([f"{mark} {model}" for model in models])
    context.out.line(
        f"{len(change.added)} new, {len(change.changed)} changed, {len(change.unchanged)} the same, "
        f"{len(change.only_on_the_box)} only on the box and kept"
    )
    context.out.line("written" if apply else "nothing written: --apply writes them")
    return OK


@memory_app.command("reembed")
@verb
async def memory_reembed(ctx: typer.Context) -> int:
    """Every fact another model embedded, embedded again by the box's; how many there were."""
    context = context_of(ctx)
    async with context.sessions.begin() as session:
        catalog = await providers.get_catalog(session)
        box_keys = await providers.box_credentials(session, context.vault)
        embedder = knowledge.embedder_for(catalog, box_keys, await context.http())
        if embedder is None:
            raise ServiceUnavailable(NO_EMBEDDER)
        count = await knowledge.reembed(session, embedder)
    context.out.line(f"{count} facts re-embedded")
    return OK


# Nothing is re-sealed that no key opens: that row is named, and the old key stays until it is 0.
@vault_app.command("rotate")
@verb
async def vault_rotate(ctx: typer.Context) -> int:
    """Every sealed value re-sealed under PINECALL_VAULT_KEY's first key; 1 while one opens not."""
    context = context_of(ctx)
    columns = await retention.reseal_everything(context.sessions, context.vault)
    context.out.rows(
        columns,
        (
            ("column", lambda c: c.column.named),
            ("re-sealed", lambda c: c.resealed),
            ("under the first key", lambda c: c.current),
            ("opened by no key", lambda c: c.unopened),
        ),
    )
    return OK if all(column.unopened == 0 for column in columns) else FOUND_WRONG
