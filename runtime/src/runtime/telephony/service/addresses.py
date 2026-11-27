"""An address of the platform's own domain given to an org's agent, as a number is bought: a mailbox on its host."""

import re
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Scope
from runtime.enums import Channel
from runtime.exceptions import Conflict, PinecallError, ServiceUnavailable, UpstreamError, ValidationError
from runtime.kit.crypto import Vault
from runtime.livekit import Servers
from runtime.telephony.repository import RouteRepository
from runtime.telephony.service import accounts as carriers
from runtime.telephony.service import number_hook
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.email_account import EmailAccount
from runtime.telephony.service.number_hook import NumberImport, Plan

VENDOR = "the platform's mail host"
TIMEOUT_S = 15.0
# The name an address is asked by: a word, before the org's own slug the platform adds after a dot.
TAKEN, REFUSED, GONE = 409, 400, 404
A_LOCAL = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
NO_HOST = "this platform gives out no addresses: its operator set no mail host (PINECALL_MAIL_HOST_URL)"


@dataclass(frozen=True, slots=True)
class MailHost:
    """Where the platform makes its addresses: the host's admin API and key, the domain, the server to reach each."""

    url: str
    key: str
    domain: str
    server: str


@dataclass(frozen=True, slots=True)
class AddressWanted:
    """An address asked for an agent: its word, the agent, the app whose flows read it, the name beside it."""

    scope: Scope
    local: str
    agent: str
    app: str | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class _Made:
    address: str
    password: str


# The org's slug follows the word, so no org takes another's (`avisos.di-camillo@agents.pinecall.io`).
# The mailbox is made first and kept as an email account of the org's, then routed as an imported
# address is: its logins are tried there, and an address that cannot be routed is removed again, so no
# mailbox is left nobody reads.
async def give_address(
    session: AsyncSession,
    vault: Vault,
    http: httpx.AsyncClient,
    servers: Servers,
    names: SipNames,
    host: MailHost | None,
    wanted: AddressWanted,
) -> Plan:
    """Make the address on the platform's mail host, keep its mailbox for the org, and route it to the agent."""
    if host is None:
        raise ServiceUnavailable(NO_HOST)
    if not A_LOCAL.match(wanted.local):
        raise ValidationError(
            f"an address is asked by a word of lowercase letters, digits and dashes, not {wanted.local!r}"
        )
    org = await accounts.get_org(session, wanted.scope.org)
    made = await _make(http, host, f"{wanted.local}.{org.slug}", wanted.label)
    account = EmailAccount(
        org=wanted.scope.org,
        address=made.address,
        password=made.password,
        imap_host=host.server,
        smtp_host=host.server,
        sender_name=wanted.label or "",
    )
    try:
        await carriers.put_carrier(session, vault, account)
        asked = NumberImport(
            wanted.scope, wanted.agent, made.address, channel=Channel.email, account=made.address, app=wanted.app
        )
        plan = await number_hook.import_number(session, vault, http, servers, names, asked)
    except PinecallError:
        await _remove(http, host, made.address)
        raise
    await RouteRepository(session).mark_managed(wanted.scope.org, made.address, Channel.email)
    return plan


async def take_address(http: httpx.AsyncClient, host: MailHost | None, address: str) -> None:
    """Remove a mailbox the platform made, when the platform has a host and the address is of its domain."""
    if host is not None and address.endswith(f"@{host.domain}"):
        await _remove(http, host, address)


async def _make(http: httpx.AsyncClient, host: MailHost, local: str, label: str | None) -> _Made:
    body = {"local": local, **({"name": label} if label else {})}
    answer = await _ask(http, host, "POST", f"/v1/domains/{host.domain}/mailboxes", body)
    if answer.status_code == TAKEN:
        raise Conflict(f"{local}@{host.domain} is taken: ask for the address by another word")
    if answer.status_code >= REFUSED:
        raise UpstreamError(f"{VENDOR} did not make {local}@{host.domain}: {answer.text[:300]}", vendor=VENDOR)
    made = answer.json()
    return _Made(address=str(made["address"]).lower(), password=str(made["password"]))


async def _remove(http: httpx.AsyncClient, host: MailHost, address: str) -> None:
    local = address.split("@", 1)[0]
    answer = await _ask(http, host, "DELETE", f"/v1/domains/{host.domain}/mailboxes/{local}", None)
    if answer.status_code >= REFUSED and answer.status_code != GONE:
        raise UpstreamError(f"{VENDOR} did not remove {address}: {answer.text[:300]}", vendor=VENDOR)


async def _ask(
    http: httpx.AsyncClient, host: MailHost, method: str, path: str, body: dict[str, str] | None
) -> httpx.Response:
    try:
        return await http.request(
            method,
            f"{host.url.rstrip('/')}{path}",
            json=body,
            headers={"Authorization": f"Bearer {host.key}"},
            timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as unreached:
        raise UpstreamError(f"{VENDOR} did not answer: {unreached}", vendor=VENDOR, retryable=True) from unreached
