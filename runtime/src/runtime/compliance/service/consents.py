"""Consent and the do-not-call list: facts about a number, never changed, the newest standing."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.compliance.models import ContactConsent
from runtime.compliance.repository.consents import ConsentRepository
from runtime.enums import ConsentKind
from runtime.exceptions import ValidationError
from runtime.kit.repository import page_of
from runtime.kit.text import parse_e164

type Standing = Literal["consented", "opted_out", "unknown"]

A_PAGE = 200
# Who the trail names for an opt-out written at an endpoint, with no form behind it.
ASKED_BY_HAND = "asked at the console or the API"


@dataclass(frozen=True, slots=True)
class Given:
    """A fact about a number, as it is written down."""

    kind: ConsentKind
    source: str
    given_by: str
    text: str | None = None
    evidence: str | None = None
    call: str | None = None


@dataclass(frozen=True, slots=True)
class History:
    """What stands for a number, and every fact about it, newest first."""

    number: str
    standing: Standing
    rows: Sequence[ContactConsent]


@dataclass(frozen=True, slots=True)
class DoNotCallPage:
    """A page of the do-not-call list: each number's opt-out, newest first, and the cursor of the next page."""

    numbers: Sequence[ContactConsent]
    next: str | None


@dataclass(frozen=True, slots=True)
class Imported:
    """What an import of numbers did: how many joined the list, and the ones that are no number."""

    added: int
    refused: list[str]


async def give_consent(session: AsyncSession, scope: Scope, number: str, given: Given) -> None:
    """Write one fact about the number in the scope's env."""
    await ConsentRepository(session).add(_fact_of(scope, parse_e164(number), given))


# Read as its sisters read a number: until 2026-11 this one trimmed it and no more, so a number its
# one caller had not parsed first would have stood as unknown beside its own rows.
async def standing_of(session: AsyncSession, scope: Scope, number: str) -> Standing:
    """What stands for the number: its newest row's, or unknown when there is none."""
    newest = await ConsentRepository(session).find_newest(scope.org, scope.env, parse_e164(number))
    return _standing_of(None if newest is None else newest.kind)


async def history_of(session: AsyncSession, scope: Scope, number: str) -> History:
    """Every fact about the number, newest first, and what stands."""
    kept = parse_e164(number)
    rows = await ConsentRepository(session).list_of_number(scope.org, scope.env, kept)
    return History(number=kept, standing=_standing_of(rows[0].kind if rows else None), rows=rows)


async def record_consent(session: AsyncSession, scope: Scope, number: str, given: Given) -> History:
    """Write one fact about a number, a consent or an opt-out; what stands for it after."""
    await give_consent(session, scope, number, given)
    return await history_of(session, scope, number)


# An opt-out is a fact, not a deletion: the consent before it stays in the history.
async def opt_out(session: AsyncSession, scope: Scope, number: str, *, by: str) -> History:
    """Put the number on the do-not-call list at somebody's word; what stands for it after."""
    return await record_consent(
        session, scope, number, Given(kind=ConsentKind.opt_out, source=ASKED_BY_HAND, given_by=by)
    )


async def list_do_not_call(
    session: AsyncSession, scope: Scope, *, after: str | None = None, limit: int = A_PAGE
) -> DoNotCallPage:
    """The env's do-not-call list, newest first, a page after the cursor."""
    rows = await ConsentRepository(session).list_opted_out(
        scope.org, scope.env, after=_parse_cursor(after), limit=limit + 1
    )
    numbers, following = page_of(rows, limit, _cursor_of)
    return DoNotCallPage(numbers=numbers, next=following)


async def has_opt_out_on(session: AsyncSession, call: str) -> bool:
    """Whether a number went on the do-not-call list on this call."""
    return await ConsentRepository(session).has_opt_out_on(call)


async def opt_out_many(session: AsyncSession, scope: Scope, numbers: Sequence[str], given: Given) -> Imported:
    """Put every number that is one on the list, in one flush; how many, and the refused."""
    kept: list[str] = []
    refused: list[str] = []
    for number in numbers:
        try:
            kept.append(parse_e164(number))
        except ValidationError:
            refused.append(number)
    await ConsentRepository(session).add_all([_fact_of(scope, number, given) for number in kept])
    return Imported(added=len(kept), refused=refused)


def _fact_of(scope: Scope, number: str, given: Given) -> ContactConsent:
    return ContactConsent(
        org=scope.org,
        env=scope.env,
        number=number,
        kind=given.kind,
        source=given.source,
        text=given.text,
        evidence=given.evidence,
        given_by=given.given_by,
        call=given.call,
    )


def _standing_of(kind: ConsentKind | None) -> Standing:
    if kind is None:
        return "unknown"
    return "opted_out" if kind is ConsentKind.opt_out else "consented"


def _cursor_of(row: ContactConsent) -> str:
    return str(row.id)


def _parse_cursor(after: str | None) -> int | None:
    if after is None:
        return None
    try:
        return int(after)
    except ValueError:
        raise ValidationError(f"{after} is no cursor of this list: the last page said it") from None
