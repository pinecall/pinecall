"""Where an org's traces go: its own OTLP collector, the headers each export carries, sealed, and whether PII rides."""

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.exceptions import NotFound, ValidationError
from runtime.kit import dns
from runtime.kit.crypto import Vault
from runtime.kit.text import a_mapping
from runtime.providers.repository import TelemetryRepository

NOT_AN_ENDPOINT = "a telemetry endpoint is an http(s) URL an OTLP exporter can post to, not {said!r}"
NOT_A_HEADER_NAME = "a telemetry header has a name"
NOT_PUBLIC = (
    "a telemetry endpoint is a collector on the internet, by its name: {host!r} is an address, a name of the "
    "box's own network, or resolves to one"
)
TRACES_GO_NOWHERE = "this org sends its traces nowhere: `pinecall telemetry set <url>` names a collector"


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

    @property
    def header_names(self) -> list[str]:
        """Which headers are set: their names, never a value."""
        return list(self.headers)


async def telemetry_of(session: AsyncSession, vault: Vault, org: str) -> Telemetry | None:
    """Where the org's traces go, headers opened; None when it sends them nowhere."""
    row = await TelemetryRepository(session).find(org)
    if row is None:
        return None
    headers: object = json.loads(vault.open(row.ciphertext)) if row.ciphertext else {}
    opened = {name: str(value) for name, value in headers.items()} if a_mapping(headers) else {}
    return Telemetry(endpoint=row.endpoint, headers=opened, pii=row.pii)


async def put_telemetry(session: AsyncSession, vault: Vault, org: str, telemetry: Telemetry) -> None:
    """Keep where the org's traces go, replacing what it had; a collector that is not on the internet is refused."""
    await check_public(telemetry.endpoint)
    ciphertext = vault.seal(json.dumps(dict(telemetry.headers))) if telemetry.headers else None
    await TelemetryRepository(session).put(org, endpoint=telemetry.endpoint, ciphertext=ciphertext, pii=telemetry.pii)


async def delete_telemetry(session: AsyncSession, org: str) -> None:
    """Forget where the org's traces went; NotFound when they went nowhere."""
    if not await TelemetryRepository(session).delete_of_org(org):
        raise NotFound(TRACES_GO_NOWHERE)


# No foreign key reaches the row from its org (`org_telemetry.org` is text): the org's erasure calls this.
async def forget_telemetry(session: AsyncSession, org: str) -> bool:
    """Forget the collector of an org that is being erased; whether it had one."""
    return await TelemetryRepository(session).delete_of_org(org)


# Until 2026-11 the endpoint was taken on its scheme alone, where every other URL a tenant hands the box
# (a mail server, a sign-in provider, a webhook) is held to the internet: a key with `providers` could aim
# the worker's exporter at an address inside the cluster. The name is checked where it is written; it may
# resolve elsewhere tomorrow, so whoever exports to it checks again, with this.
async def check_public(endpoint: str) -> None:
    """Refuse a collector whose host is an address, a local name, or a name that resolves anywhere but the internet."""
    host = urlsplit(endpoint).hostname or ""
    if not await asyncio.to_thread(dns.public_addresses, host):
        raise ValidationError(NOT_PUBLIC.format(host=host))
