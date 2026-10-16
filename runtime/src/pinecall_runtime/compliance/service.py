"""The compliance rules: the policy and its sentences, the access log, recording keys, telemetry."""

import base64
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.compliance.repository import (
    PolicyRepository,
    ReadRepository,
    RecordingKeyRepository,
    TelemetryRepository,
)
from pinecall_runtime.compliance.schemas import (
    CallingHours,
    OrgPolicy,
    OrgPolicyRow,
    ReadRow,
    TelemetryResponse,
)
from pinecall_runtime.enums import ReadKind
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.sealed_audio import new_key
from pinecall_runtime.kit.text import a_mapping

logger = logging.getLogger(__name__)

# Who reads, or erases, on the box's own behalf: off the box, or through its own endpoints.
OPERATOR = "operator"

NOT_AN_ENDPOINT = "a telemetry endpoint is an http(s) URL an OTLP exporter can post to, not {said!r}"
NOT_A_HEADER_NAME = "a telemetry header has a name"
TRACES_GO_NOWHERE = "this org sends its traces nowhere: PUT /v1/telemetry names a collector"

# The platform's sentences, by the first part of the agent's language; English for any other.
CALLING_FOR = {
    "en": "This is an automated assistant calling on behalf of {org}.",
    "es": "Le habla un asistente automático en nombre de {org}.",
    "pt": "Aqui fala um assistente automático em nome de {org}.",
    "fr": "Ici un assistant automatique qui appelle au nom de {org}.",
    "de": "Hier spricht ein automatischer Assistent im Auftrag von {org}.",
    "it": "Sono un assistente automatico che chiama per conto di {org}.",
}
MAY_BE_RECORDED = {
    "en": "This call may be recorded.",
    "es": "Esta llamada puede ser grabada.",
    "pt": "Esta chamada pode ser gravada.",
    "fr": "Cet appel peut être enregistré.",
    "de": "Dieser Anruf kann aufgezeichnet werden.",
    "it": "Questa chiamata può essere registrata.",
}
FALLBACK_LANGUAGE = "en"


# ── the policy, and what a call says first ──


async def policy_of(session: AsyncSession, org: str) -> OrgPolicyRow:
    """The org's policy and who set it last; an org nobody set has the platform's defaults."""
    row = await PolicyRepository(session).get(org)
    if row is None:
        return OrgPolicyRow(policy=OrgPolicy(), set_by=None, set_at=None)
    hours = None
    if row.calling_from is not None and row.calling_until is not None:
        hours = CallingHours.model_validate({"from": row.calling_from, "until": row.calling_until})
    policy = OrgPolicy(
        retention_days=row.retention_days,
        calling_hours=hours,
        per_number_day=row.per_number_day,
        consent_everywhere=row.consent_everywhere,
        disclosure=row.disclosure,
        recording_notice=row.recording_notice,
    )
    return OrgPolicyRow(policy=policy, set_by=row.set_by, set_at=row.set_at.timestamp())


async def put_policy(session: AsyncSession, org: str, policy: OrgPolicy, *, by: str) -> OrgPolicyRow:
    """Replace the org's policy whole; the row as it now stands."""
    hours = policy.calling_hours
    await PolicyRepository(session).put(
        org,
        retention_days=policy.retention_days,
        calling_from=None if hours is None else hours.from_,
        calling_until=None if hours is None else hours.until,
        per_number_day=policy.per_number_day,
        consent_everywhere=policy.consent_everywhere,
        disclosure=policy.disclosure,
        recording_notice=policy.recording_notice,
        set_by=by,
    )
    return await policy_of(session, org)


def disclosure_of(policy: OrgPolicy, org_name: str, language: str | None) -> str | None:
    """An outbound call's first sentence: the org's own, else the platform's, or None."""
    if policy.disclosure is not None:
        return policy.disclosure.strip() or None
    return CALLING_FOR[_spoken(language)].format(org=org_name)


def notice_of(policy: OrgPolicy, language: str | None) -> str | None:
    """The sentence a recorded call says, or None when the org turned the notice off."""
    return MAY_BE_RECORDED[_spoken(language)] if policy.recording_notice else None


def _spoken(language: str | None) -> str:
    first = (language or FALLBACK_LANGUAGE).replace("_", "-").split("-")[0].lower()
    return first if first in CALLING_FOR else FALLBACK_LANGUAGE


# ── who read what ──


# A record that cannot be written is said in the log and the read goes on: an audit that fails a
# read would be a way to stop every read. The savepoint keeps the session usable after it.
async def record_read(session: AsyncSession, scope: Scope, subject: str, what: ReadKind, *, by: str) -> None:
    """Write down who read the subject, and what of it; once an hour per reader."""
    try:
        async with session.begin_nested():
            await ReadRepository(session).record(scope.org, scope.env, subject, what, by)
    except SQLAlchemyError:
        logger.warning("the read of %s by %s went unrecorded; the read goes on", subject, by, exc_info=True)


async def list_reads(session: AsyncSession, org: str, *, subject: str | None = None) -> list[ReadRow]:
    """The org's reads, newest first, of one call or number when named."""
    rows = await ReadRepository(session).of_org(org, subject=subject)
    return [
        ReadRow(subject=row.subject, what=row.what, env=row.env, reader=row.reader, at=row.at.timestamp())
        for row in rows
    ]


# ── a recording's key ──


async def recording_key_for(session: AsyncSession, vault: Vault, org: str, call: str) -> bytes | None:
    """The call's recording key, made now or before; None for another org's call."""
    fresh = vault.seal(base64.urlsafe_b64encode(new_key()).decode())
    sealed = await RecordingKeyRepository(session).mint(call, org, fresh)
    return None if sealed is None else base64.urlsafe_b64decode(vault.open(sealed))


async def recording_key_of(session: AsyncSession, vault: Vault, call: str) -> bytes | None:
    """The call's recording key; None when it was never recorded sealed."""
    row = await RecordingKeyRepository(session).get(call)
    return None if row is None else base64.urlsafe_b64decode(vault.open(row.sealed))


# ── where the org's traces go ──


@dataclass(frozen=True, slots=True)
class Telemetry:
    """An org's OTLP collector: the endpoint, the headers every export carries, and PII."""

    endpoint: str
    headers: Mapping[str, str] = field(default_factory=dict[str, str])
    # Whether a span carries what was said and what a tool got; stripped before export otherwise.
    pii: bool = False

    def __post_init__(self) -> None:
        if not self.endpoint.startswith(("http://", "https://")):
            raise ValidationError(NOT_AN_ENDPOINT.format(said=self.endpoint))
        if any(not name.strip() for name in self.headers):
            raise ValidationError(NOT_A_HEADER_NAME)


async def telemetry_of(session: AsyncSession, vault: Vault, org: str) -> Telemetry | None:
    """Where the org's traces go, headers opened; None when it sends them nowhere."""
    row = await TelemetryRepository(session).get(org)
    if row is None:
        return None
    headers: object = json.loads(vault.open(row.ciphertext)) if row.ciphertext else {}
    opened = {name: str(value) for name, value in headers.items()} if a_mapping(headers) else {}
    return Telemetry(endpoint=row.endpoint, headers=opened, pii=row.pii)


async def describe_telemetry(session: AsyncSession, vault: Vault, org: str) -> TelemetryResponse | None:
    """The row as the org reads it back: the endpoint, which headers are set, PII; never a value."""
    found = await telemetry_of(session, vault, org)
    if found is None:
        return None
    return TelemetryResponse(endpoint=found.endpoint, header_names=list(found.headers), pii=found.pii)


async def put_telemetry(session: AsyncSession, vault: Vault, org: str, telemetry: Telemetry) -> None:
    """Keep where the org's traces go, replacing what it had."""
    ciphertext = vault.seal(json.dumps(dict(telemetry.headers))) if telemetry.headers else None
    await TelemetryRepository(session).put(org, endpoint=telemetry.endpoint, ciphertext=ciphertext, pii=telemetry.pii)


async def drop_telemetry(session: AsyncSession, org: str) -> None:
    """Forget where the org's traces went; NotFound when they went nowhere."""
    if not await TelemetryRepository(session).drop(org):
        raise NotFound(TRACES_GO_NOWHERE)
