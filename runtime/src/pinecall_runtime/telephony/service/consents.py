"""Consent and the do-not-call list: facts about a number, never changed, the newest standing."""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.enums import ConsentKind
from pinecall_runtime.exceptions import ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import parse_e164
from pinecall_runtime.telephony.repository import ConsentRepository
from pinecall_runtime.telephony.schemas import ConsentHistory, ConsentRow, DoNotCall, OptedOut

type Standing = Literal["consented", "opted_out", "unknown"]

A_PAGE = 200


@dataclass(frozen=True, slots=True)
class Given:
    """A fact about a number, as it is written down."""

    kind: ConsentKind
    source: str
    given_by: str
    text: str | None = None
    evidence: str | None = None
    call: str | None = None


async def give_consent(session: AsyncSession, scope: Scope, number: str, given: Given) -> None:
    """Write one fact about the number in the scope's env."""
    await ConsentRepository(session).give(
        scope.org,
        scope.env,
        parse_e164(number),
        kind=given.kind,
        source=given.source,
        given_by=given.given_by,
        text_=given.text,
        evidence=given.evidence,
        call=given.call,
    )


async def standing_of(session: AsyncSession, scope: Scope, number: str) -> Standing:
    """What stands for the number: its newest row's, or unknown when there is none."""
    newest = await ConsentRepository(session).newest(scope.org, scope.env, number.strip())
    return _as_standing(None if newest is None else newest.kind)


async def history_of(session: AsyncSession, scope: Scope, number: str) -> ConsentHistory:
    """Every fact about the number, newest first, and what stands."""
    kept = parse_e164(number)
    rows = await ConsentRepository(session).history(scope.org, scope.env, kept)
    listed = [
        ConsentRow(
            kind=row.kind,
            source=row.source,
            text=row.text,
            evidence=row.evidence,
            given_by=row.given_by,
            call=row.call,
            given_at=row.given_at.timestamp(),
        )
        for row in rows
    ]
    return ConsentHistory(number=kept, standing=_as_standing(listed[0].kind if listed else None), rows=listed)


async def do_not_call(
    session: AsyncSession, scope: Scope, *, after: str | None = None, limit: int = A_PAGE
) -> DoNotCall:
    """The env's do-not-call list, newest first, a page after the cursor."""
    rows = await ConsentRepository(session).opted_out(scope.org, scope.env, after=_cursor(after), limit=limit)
    numbers = [
        OptedOut(number=str(number), since=given_at.timestamp(), source=str(source), given_by=str(by))
        for _, number, given_at, source, by in rows
    ]
    last = rows[-1] if len(rows) == limit else None
    return DoNotCall(numbers=numbers, next=None if last is None else str(last[0]))


async def opted_out_on(session: AsyncSession, call: str) -> bool:
    """Whether a number went on the do-not-call list on this call."""
    return await ConsentRepository(session).opted_out_on(call)


async def opt_out_many(session: AsyncSession, scope: Scope, numbers: list[str], given: Given) -> tuple[int, list[str]]:
    """Put every number that is one on the list, in one flush; how many, and the refused."""
    kept: list[str] = []
    refused: list[str] = []
    for number in numbers:
        try:
            kept.append(parse_e164(number))
        except ValidationError:
            refused.append(number)
    await ConsentRepository(session).give_many(
        scope.org, scope.env, kept, kind=given.kind, source=given.source, given_by=given.given_by
    )
    return len(kept), refused


def _as_standing(kind: ConsentKind | None) -> Standing:
    if kind is None:
        return "unknown"
    return "opted_out" if kind is ConsentKind.opt_out else "consented"


def _cursor(after: str | None) -> int | None:
    if after is None:
        return None
    try:
        return int(after)
    except ValueError:
        raise ValidationError(f"{after} is no cursor of this list: the last page said it") from None
