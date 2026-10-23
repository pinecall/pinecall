"""Where alerts go: an org's own URL, and the operator's, which every org's alerts reach too."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.alerts.repository import WebhookRepository
from pinecall_runtime.exceptions import NotFound, ValidationError
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.platform import service as platform

NOT_A_URL = "a webhook is an http(s) URL an alert can be posted to, not {said!r}"
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
