"""The org's policy: how long calls are kept, when a number may ring, and the sentences a call says first."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.compliance.models import OrgPolicy
from runtime.compliance.repository.policy import PolicyRepository

# The platform's sentences, by the first part of the agent's language; English for any other.
CALLING_FOR = {
    "en": "This is an automated assistant calling on behalf of {org}.",
    "es": "Le habla un asistente automático en nombre de {org}.",
    "pt": "Aqui fala um assistente automático em nome de {org}.",
    "fr": "Ici un assistant automatique qui appelle au nom de {org}.",
    "de": "Hier spricht ein automatischer Assistent im Auftrag von {org}.",
    "it": "Sono un assistente automatico che chiama per conto di {org}.",
    "ar": "هذا مساعد آلي يتصل بالنيابة عن {org}.",
}
MAY_BE_RECORDED = {
    "en": "This call may be recorded.",
    "es": "Esta llamada puede ser grabada.",
    "pt": "Esta chamada pode ser gravada.",
    "fr": "Cet appel peut être enregistré.",
    "de": "Dieser Anruf kann aufgezeichnet werden.",
    "it": "Questa chiamata può essere registrata.",
    "ar": "قد يتم تسجيل هذه المكالمة.",
}
FALLBACK_LANGUAGE = "en"


@dataclass(frozen=True, slots=True)
class Hours:
    """The hours of the called number's own day a call may ring: from, until (exclusive)."""

    from_: int
    until: int


# What every other domain reads of the policy: a value, never the body an endpoint took. Until 2026-11
# `policy_of` answered the PUT's own body, and the dial guards, a call's opening and a simulation read
# `.policy.calling_hours.from_` off a request shape.
@dataclass(frozen=True, slots=True)
class Policy:
    """What the org owes callers: how long calls are kept, when a number may ring, what a call says first."""

    # None keeps calls until the org erases them.
    retention_days: int | None = None
    calling_hours: Hours | None = None
    per_number_day: int | None = None
    consent_everywhere: bool = False
    # An outbound call's opening sentence: None is the platform's, "" is none.
    disclosure: str | None = None
    recording_notice: bool = True
    # Who set it last, and when; None on an org nobody set one for.
    set_by: str | None = None
    set_at: datetime | None = None

    def disclosure_for(self, org_name: str, language: str | None) -> str | None:
        """An outbound call's first sentence: the org's own, else the platform's, or None."""
        if self.disclosure is not None:
            return self.disclosure.strip() or None
        return CALLING_FOR[_language_of(language)].format(org=org_name)

    def notice_in(self, language: str | None) -> str | None:
        """The sentence a recorded call says, or None when the org turned the notice off."""
        return MAY_BE_RECORDED[_language_of(language)] if self.recording_notice else None


async def policy_of(session: AsyncSession, org: str) -> Policy:
    """The org's policy and who set it last; an org nobody set has the platform's defaults."""
    row = await PolicyRepository(session).find(org)
    return Policy() if row is None else _policy_of(row)


async def put_policy(session: AsyncSession, org: str, policy: Policy, *, by: str) -> Policy:
    """Replace the org's policy whole; the policy as it now stands."""
    return _policy_of(await PolicyRepository(session).put(org, _columns_of(policy), by=by))


# The one mapping between the row and the value, each way: a setting added to the policy is added here.
def _policy_of(row: OrgPolicy) -> Policy:
    hours = None
    if row.calling_from is not None and row.calling_until is not None:
        hours = Hours(row.calling_from, row.calling_until)
    return Policy(
        retention_days=row.retention_days,
        calling_hours=hours,
        per_number_day=row.per_number_day,
        consent_everywhere=row.consent_everywhere,
        disclosure=row.disclosure,
        recording_notice=row.recording_notice,
        set_by=row.set_by,
        set_at=row.set_at,
    )


def _columns_of(policy: Policy) -> dict[str, Any]:
    hours = policy.calling_hours
    return {
        "retention_days": policy.retention_days,
        "calling_from": None if hours is None else hours.from_,
        "calling_until": None if hours is None else hours.until,
        "per_number_day": policy.per_number_day,
        "consent_everywhere": policy.consent_everywhere,
        "disclosure": policy.disclosure,
        "recording_notice": policy.recording_notice,
    }


def _language_of(language: str | None) -> str:
    first = (language or FALLBACK_LANGUAGE).replace("_", "-").split("-")[0].lower()
    return first if first in CALLING_FOR else FALLBACK_LANGUAGE
