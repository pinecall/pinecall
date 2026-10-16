"""`doctor`: each thing the box needs, examined, a line each; the exit is 1 when one is wrong."""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import typer
from livekit import api
from livekit.protocol.room import ListRoomsRequest
from sqlalchemy.exc import SQLAlchemyError

from pinecall_runtime.calls import service as calls
from pinecall_runtime.cli.command import FOUND_WRONG, OK, Context, context_of, verb
from pinecall_runtime.exceptions import PinecallError
from pinecall_runtime.fleet import service as fleet
from pinecall_runtime.platform import service as platform

BEHIND = "{logs}: rows past their head's seq, of {examined} heads examined"
APART = "facts not what their log folds to, of {sample} sampled: {calls}"
WAITED_S = 5.0


@dataclass(frozen=True, slots=True)
class Finding:
    """One examination: what was examined, what is wrong with it (None for nothing), and its state."""

    name: str
    trouble: str | None
    state: str = ""


@verb
async def doctor(ctx: typer.Context) -> int:
    """Each thing the box needs, a line each; the exit is 1 when one is missing."""
    context = context_of(ctx)
    findings = [
        Finding("vault", _vault(context)),
        await _examined("database", _database, context),
        await _examined("facts", _facts, context),
        await _examined("days", _days, context),
        await _examined("offers", _offers, context),
        await _examined("archive", _archive, context),
        Finding("livekit", await _livekit(context)),
        Finding("gateway", await _gateway(context)),
    ]
    if context.out.as_json:
        context.out.data(findings)
    else:
        for finding in findings:
            why = (
                f": {finding.trouble}"
                if finding.trouble is not None
                else (f": {finding.state}" if finding.state else "")
            )
            context.out.line(f"{'ok' if finding.trouble is None else 'NO'}  {finding.name}{why}")
    return OK if all(finding.trouble is None for finding in findings) else FOUND_WRONG


type Examine = Callable[[Context], Awaitable[Finding]]


# A database that cannot be reached fails the one line, and the next lines are still examined.
async def _examined(name: str, examine: Examine, context: Context) -> Finding:
    try:
        return await examine(context)
    except (PinecallError, SQLAlchemyError, OSError) as refused:
        return Finding(name, str(refused))


def _vault(context: Context) -> str | None:
    try:
        _ = context.vault
    except PinecallError as refused:
        return str(refused)
    return None


async def _database(context: Context) -> Finding:
    standing = await platform.schema_standing(context.engine)
    if not standing.behind:
        return Finding("database", None, f"at {standing.head}")
    pending = len(standing.history_pending)
    return Finding("database", f"behind: {pending} history files pending, at revision {standing.current or 'none'}")


async def _facts(context: Context) -> Finding:
    async with context.sessions() as session:
        heads = await calls.heads_behind(session)
        apart = await calls.differing(session, sample=calls.A_SAMPLE)
    troubles: list[str] = []
    if heads.behind:
        troubles.append(BEHIND.format(logs=", ".join(heads.behind), examined=heads.examined))
    if apart:
        named = ", ".join(f"{item.call} ({', '.join(item.columns)})" for item in apart)
        troubles.append(APART.format(sample=calls.A_SAMPLE, calls=named))
    return Finding("facts", "; ".join(troubles) or None)


async def _days(context: Context) -> Finding:
    async with context.sessions() as session:
        return Finding("days", await calls.examine_days(session, time.time()))


async def _offers(context: Context) -> Finding:
    offering = fleet.Offering(context.sessions, await context.servers(), fleet.Roster())
    return Finding("offers", await offering.examine(time.time()))


async def _archive(context: Context) -> Finding:
    async with context.sessions() as session:
        archive = await platform.archive_of(session, context.settings.wal_spool)
    trouble, state = platform.archive_finding(archive, datetime.now(UTC))
    return Finding("archive", trouble, state)


# Each env's LiveKit is asked, and the one that does not answer is named.
async def _livekit(context: Context) -> str | None:
    try:
        servers = await context.servers()
    except PinecallError as refused:
        return str(refused)
    failed: list[str] = []
    for env, server in servers.items():
        try:
            await server.room.list_rooms(ListRoomsRequest())
        except (api.TwirpError, OSError) as refused:
            failed.append(f"{env} ({context.settings.livekit_url_of(env)}): {refused}")
    return "; ".join(failed) or None


async def _gateway(context: Context) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=WAITED_S) as http:
            answer = await http.get(f"{context.settings.gateway_url}/v1/docs")
    except httpx.HTTPError as unreachable:
        return str(unreachable)
    return None if answer.status_code < httpx.codes.BAD_REQUEST else f"answered {answer.status_code}"
