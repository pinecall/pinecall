"""`sessions`: the log read back off Postgres: the newest calls, one call whole or folded, a call followed."""

import json
from dataclasses import dataclass
from typing import Annotated

import typer

from pinecall_runtime.calls import service as calls
from pinecall_runtime.cli.command import FOUND_WRONG, OK, Context, context_of, verb
from pinecall_runtime.cli.output import when
from pinecall_runtime.compliance import service as compliance
from pinecall_runtime.enums import ReadKind
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.wire.base import Entry
from pinecall_runtime.wire.events import TERMINAL_EVENT, CallSummary

app = typer.Typer(help="the log, off Postgres", no_args_is_help=True)

NO_SUCH_CALL = "no call {call} was ever written here"
NOT_RECORDED = "call {call} was not recorded: its call.summary carries no path"
NO_LIVE_CALL = "no call is open right now"


@dataclass(frozen=True, slots=True)
class Listed:
    """One call as `sessions list` shows it: its id, its agent, and its facts when it has a row."""

    call: str
    agent: str | None
    facts: calls.CallFacts | None


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
        newest = await calls.newest_calls(session, limit, agent=agent)
        facts = await calls.facts_of_calls(session, newest)
        heads = {call: await calls.head_of_call(session, call) for call in newest}
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
        context.out.data(calls.reduce(entries))
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
    store = calls.Store(context.sessions)
    async with context.sessions() as session:
        named = call or await calls.newest_live_call(session)
        if named is None:
            raise NotFound(NO_LIVE_CALL)
        await _read_by_the_operator(context, named, ReadKind.log)
    async for entry in calls.Logs(store).reading(named).stream():
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
    entries = await calls.Store(context.sessions).whole(call)
    if not entries:
        raise NotFound(NO_SUCH_CALL.format(call=call))
    await _read_by_the_operator(context, call, what)
    return entries


# The operator reading an org's call off the box is a read the org's access log shows.
async def _read_by_the_operator(context: Context, call: str, what: ReadKind) -> None:
    async with context.sessions.begin() as session:
        head = await calls.head_of_call(session, call)
        if head is not None and head.scope is not None:
            await compliance.record_read(session, head.scope, call, what, by=compliance.OPERATOR)


def _agent_of(head: calls.CallHead | None) -> str | None:
    return None if head is None else head.agent


def _reason_of(row: Listed) -> str:
    return "open" if row.facts is None or row.facts.end_reason is None else row.facts.end_reason


def _line(entry: Entry) -> str:
    data = json.dumps(entry.data, ensure_ascii=False)
    return f"{entry.seq:>5}  {when(entry.ts)}  {entry.type:24}  {data}"
