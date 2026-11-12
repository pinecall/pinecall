"""`memory`: contact memory, embedded again by the box's embedder after the providers row names another."""

import typer

from runtime.cli.command import OK, context_of, verb
from runtime.exceptions import ServiceUnavailable
from runtime.knowledge.service import memory
from runtime.knowledge.service.embedder import embedder_of
from runtime.scoping import box_wide

app = typer.Typer(help="contact memory", no_args_is_help=True)


# A batch at a time, each in transactions of its own: a run cut short leaves what it did, and the next
# run skips it. The box's own terminal names no org: every org's and env's facts.
@app.command("reembed")
@verb
async def memory_reembed(ctx: typer.Context) -> int:
    """Every fact another model embedded, embedded again by the box's; how many there were."""
    context = context_of(ctx)
    handles = await context.handles()
    with box_wide():
        async with handles.sessions() as session:
            embedder = await embedder_of(session, handles.vault, handles.http)
        if embedder is None:
            raise ServiceUnavailable("this box embeds nothing: no embedding in its providers row")
        count = 0
        while done := await memory.embed_stale(handles.sessions, embedder):
            count += done
    context.out.line(f"{count} facts re-embedded")
    return OK
