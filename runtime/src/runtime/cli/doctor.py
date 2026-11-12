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

from runtime.calls.service import days, refold
from runtime.cli.command import FOUND_WRONG, OK, Context, context_of, verb
from runtime.exceptions import PinecallError
from runtime.fleet.service import offers
from runtime.platform.service import database, schema

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
        Finding("vault", _examine_vault(context)),
        await _examine("database", _database, context),
        await _examine("facts", _facts, context),
        await _examine("days", _days, context),
        await _examine("offers", _offers, context),
        await _examine("archive", _archive, context),
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
async def _examine(name: str, examine: Examine, context: Context) -> Finding:
    try:
        return await examine(context)
    except (PinecallError, SQLAlchemyError, OSError) as refused:
        return Finding(name, str(refused))


def _examine_vault(context: Context) -> str | None:
    try:
        _ = context.vault
    except PinecallError as refused:
        return str(refused)
    return None


async def _database(context: Context) -> Finding:
    standing = await schema.standing_of(context.engine)
    if not standing.behind:
        return Finding("database", None, f"at {standing.head}")
    pending = len(standing.history_pending)
    return Finding("database", f"behind: {pending} history files pending, at revision {standing.current or 'none'}")


async def _facts(context: Context) -> Finding:
    async with context.sessions() as session:
        heads = await refold.examine_heads(session)
        apart = await refold.list_differing(session, sample=refold.A_SAMPLE)
    troubles: list[str] = []
    if heads.behind:
        troubles.append(BEHIND.format(logs=", ".join(heads.behind), examined=heads.examined))
    if apart:
        named = ", ".join(f"{item.call} ({', '.join(item.columns)})" for item in apart)
        troubles.append(APART.format(sample=refold.A_SAMPLE, calls=named))
    return Finding("facts", "; ".join(troubles) or None)


async def _days(context: Context) -> Finding:
    async with context.sessions() as session:
        return Finding("days", await days.examine_days(session, time.time()))


async def _offers(context: Context) -> Finding:
    async with context.sessions() as session:
        return Finding("offers", await offers.examine(session, time.time()))


async def _archive(context: Context) -> Finding:
    async with context.sessions() as session:
        archive = await database.archive_of(session, context.settings.wal_spool)
    judged = database.judge_archive(archive, datetime.now(UTC))
    return Finding("archive", judged.trouble, judged.state)


# Each env's LiveKit is asked, and the one that does not answer is named.
async def _livekit(context: Context) -> str | None:
    try:
        servers = (await context.handles()).servers
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
