"""Where alerts go: an org's own URL, and the operator's, which every org's alerts reach too."""

import asyncio
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.alerts.repository import WebhookRepository
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.kit import dns
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.platform import service as platform

NOT_A_URL = "a webhook is an http(s) URL an alert can be posted to, not {said!r}"
NOT_ON_THE_INTERNET = (
    "a webhook is posted to the public internet: {host} is a private, local or link-local address, "
    "which the box must not reach on an org's word"
)
NOT_RESOLVED = "a webhook is posted to a host that resolves: {host} does not"
ALERTS_GO_NOWHERE = "this org posts its alerts nowhere: `pinecall webhook set <url>` names a URL"
THE_OPERATOR_HEARS_NOTHING = (
    "the box posts its orgs' alerts nowhere: `pinecall-runtime box alerts set <url>` names a URL"
)
# The box setting the operator's URL is kept under; its secret sealed beside it.
OPERATOR_ALERTS = "alerts"


@dataclass(frozen=True, slots=True)
class Webhook:
    """The URL the org's alerts are posted to, and the secret each post is signed with."""

    url: str
    secret: str | None = None

    def __post_init__(self) -> None:
        if not self.url.startswith(("http://", "https://")):
            raise ValidationError(NOT_A_URL.format(said=self.url))


async def webhook_of(session: AsyncSession, vault: Vault, org: str) -> Webhook | None:
    """Where the org's alerts go, secret opened; None when they go nowhere."""
    row = await WebhookRepository(session).get(org)
    if row is None:
        return None
    return Webhook(url=row.url, secret=vault.open(row.ciphertext) if row.ciphertext else None)


# The box posts to this URL on the org's word: one that resolves inside the box, the cluster or a
# private network would make it a door into them, so the door resolves the host and holds it to the
# internet before the service keeps it.
async def check_reaches_the_internet(webhook: Webhook) -> None:
    """Refuse a URL whose host is local, private or link-local, or resolves to such an address."""
    host = (urlsplit(webhook.url).hostname or "").lower()
    if not host or host == "localhost" or host.endswith(dns.LOCAL_SUFFIXES):
        raise ValidationError(NOT_ON_THE_INTERNET.format(host=host or webhook.url))
    try:
        addresses = await asyncio.to_thread(dns.resolve, host)
    except OSError as unresolved:
        raise ValidationError(NOT_RESOLVED.format(host=host)) from unresolved
    if not dns.all_public(addresses):
        raise ValidationError(NOT_ON_THE_INTERNET.format(host=host))


async def put_webhook(session: AsyncSession, vault: Vault, org: str, webhook: Webhook) -> None:
    """Keep where the org's alerts go, replacing what it had."""
    ciphertext = None if webhook.secret is None else vault.seal(webhook.secret)
    await WebhookRepository(session).put(org, url=webhook.url, ciphertext=ciphertext)


async def delete_webhook(session: AsyncSession, org: str) -> None:
    """Forget where the org's alerts went; NotFound when they went nowhere."""
    if not await WebhookRepository(session).drop(org):
        raise NotFound(ALERTS_GO_NOWHERE)


async def test_webhook(session: AsyncSession, vault: Vault, org: str) -> Webhook:
    """The webhook a test post goes to; refused when the org set none."""
    found = await webhook_of(session, vault, org)
    if found is None:
        raise NotFound(ALERTS_GO_NOWHERE)
    return found


# The operator reads every org's alerts as the org does, the same post: what breaks for a tenant
# is the box's to see, whether or not the tenant named a URL of its own.
async def operator_webhook_of(session: AsyncSession, vault: Vault) -> Webhook | None:
    """Where the operator hears every org's alerts, secret opened; None when nowhere."""
    sealed = await platform.get_sealed_setting(session, OPERATOR_ALERTS)
    if sealed is not None:
        value, ciphertext = sealed
        return Webhook(url=str(value["url"]), secret=vault.open(ciphertext))
    unsigned = await platform.get_setting(session, OPERATOR_ALERTS)
    return None if unsigned is None else Webhook(url=str(unsigned["url"]))


async def put_operator_webhook(session: AsyncSession, vault: Vault, webhook: Webhook) -> None:
    """Keep where the operator hears every org's alerts, replacing what the box had."""
    ciphertext = None if webhook.secret is None else vault.seal(webhook.secret)
    await platform.put_setting(session, OPERATOR_ALERTS, {"url": webhook.url}, ciphertext=ciphertext)


async def delete_operator_webhook(session: AsyncSession) -> None:
    """Forget where the operator heard the alerts; NotFound when it heard them nowhere."""
    if not await platform.delete_setting(session, OPERATOR_ALERTS):
        raise NotFound(THE_OPERATOR_HEARS_NOTHING)
