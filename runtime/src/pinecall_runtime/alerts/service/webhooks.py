"""Where an org's alerts go: a URL of its own, every post signed when it set a secret."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.alerts.repository import WebhookRepository
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.kit.crypto import Vault

NOT_A_URL = "a webhook is an http(s) URL an alert can be posted to, not {said!r}"
ALERTS_GO_NOWHERE = "this org posts its alerts nowhere: `pinecall webhook set <url>` names a URL"


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
