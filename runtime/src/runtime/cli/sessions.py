"""`sessions`: the log read back off Postgres: the newest calls, one call whole or folded, a call followed."""

import json
from dataclasses import dataclass
from typing import Annotated

import typer

from runtime import builders
from runtime.calls.folds.facts import CallFacts
from runtime.calls.folds.state import reduce
from runtime.calls.service import CallHead, lists
from runtime.cli.command import FOUND_WRONG, OK, Context, context_of, verb
from runtime.cli.output import when
from runtime.compliance.service import reads
from runtime.enums import ReadKind
from runtime.exceptions import NotFound
from runtime.scoping import box_wide
from runtime.wire.base import Entry
from runtime.wire.events import TERMINAL_EVENT, CallSummary

app = typer.Typer(help="the log, off Postgres", no_args_is_help=True)

NOT_RECORDED = "call {call} was not recorded: its call.summary carries no path"


@dataclass(frozen=True, slots=True)
class Listed:
    """One call as `sessions list` shows it: its id, its agent, and its facts when it has a row."""

    call: str
    agent: str | None
    facts: CallFacts | None


@app.command("list")
@verb
async def sessions_list(
    ctx: typer.Context,
    agent: Annotated[str | None, typer.Option("--agent", help="One agent's calls.")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 20,
) -> int:
    """The newest calls of the box, or of one agent: when, whose, how they ended."""
    context = context_of(ctx)
    async with context.sessions() as session:
        with box_wide():
            newest = await lists.list_newest_calls(session, limit, agent=agent)
            facts = await lists.facts_of_calls(session, newest)
            heads = {call: await lists.find_head(session, call) for call in newest}
    rows = [Listed(call, _agent_of(heads[call]), facts.get(call)) for call in newest]
    context.out.rows(
        rows,
        (
            ("call", lambda row: row.call),
            ("agent", lambda row: row.agent),
            ("channel", lambda row: None if row.facts is None else row.facts.channel),
            ("ended", lambda row: None if row.facts is None else when(row.facts.ended_at)),
            ("reason", _reason_of),
            ("outcome", lambda row: None if row.facts is None else row.facts.outcome),
        ),
    )
    return OK


@app.command("show")
@verb
async def sessions_show(
    ctx: typer.Context,
    call: str,
    folded: Annotated[bool, typer.Option("--folded", help="The state the log folds to, as JSON.")] = False,
) -> int:
    """One call's log printed whole, entry by entry, or the state it folds to."""
    context = context_of(ctx)
    entries = await _whole(context, call, ReadKind.log)
    if folded:
        context.out.data(reduce(entries))
    elif context.out.as_json:
        context.out.data(entries)
    else:
        context.out.lines([_line(entry) for entry in entries])
    return OK


@app.command("tail")
@verb
async def sessions_tail(
    ctx: typer.Context, call: Annotated[str | None, typer.Argument(help="A call; none named, the newest live.")] = None
) -> int:
    """A call followed as it is written, until it seals."""
    context = context_of(ctx)
    handles = await context.handles()
    *_, logs = builders.build_log_engine(handles, context.stack)
    async with handles.sessions() as session:
        named = call or await lists.find_newest_live_call(session)
    if named is None:
        raise NotFound("no call is open right now")
    await _read_by_the_operator(context, named, ReadKind.log)
    async for entry in logs.stream(named):
        context.out.line(json.dumps(entry.dump()) if context.out.as_json else _line(entry))
        if entry.type == TERMINAL_EVENT:
            return OK
    return OK


@app.command("recording")
@verb
async def sessions_recording(ctx: typer.Context, call: str) -> int:
    """The path the call's audio was written to; 1 when it kept none."""
    context = context_of(ctx)
    entries = await _whole(context, call, ReadKind.recording)
    summary = next((entry for entry in reversed(entries) if entry.type == "call.summary"), None)
    path = None if summary is None else CallSummary.model_validate(summary.data).recording
    if path is None:
        context.out.warn(NOT_RECORDED.format(call=call))
        return FOUND_WRONG
    context.out.secret(path)
    return OK


async def _whole(context: Context, call: str, what: ReadKind) -> list[Entry]:
    async with context.sessions() as session:
        with box_wide():
            entries = await lists.list_entries(session, call)
    if not entries:
        raise NotFound(f"no call {call} was ever written here")
    await _read_by_the_operator(context, call, what)
    return entries


# The operator reading an org's call off the box is a read the org's access log shows.
async def _read_by_the_operator(context: Context, call: str, what: ReadKind) -> None:
    async with context.sessions.begin() as session:
        with box_wide():
            head = await lists.find_head(session, call)
        if head is not None and head.scope is not None:
            await reads.record_read(session, head.scope, call, what, by=reads.OPERATOR)


def _agent_of(head: CallHead | None) -> str | None:
    return None if head is None else head.agent


def _reason_of(row: Listed) -> str:
    return "open" if row.facts is None or row.facts.end_reason is None else row.facts.end_reason


def _line(entry: Entry) -> str:
    data = json.dumps(entry.data, ensure_ascii=False)
    return f"{entry.seq:>5}  {when(entry.ts)}  {entry.type:24}  {data}"
