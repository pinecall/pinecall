"""Where alerts go: an org's own URL and the operator's, the signed post, the alerts waiting for theirs, the test."""

import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.alerts.models import Alert
from runtime.alerts.repository import AlertRepository, WebhookRepository
from runtime.alerts.service import kinds
from runtime.exceptions import NotFound, ValidationError
from runtime.kit import dns
from runtime.kit.crypto import Vault
from runtime.kit.loops import survive
from runtime.kit.text import JsonObject
from runtime.kit.time import epoch, now
from runtime.platform import service as platform
from runtime.scoping import box_wide

logger = logging.getLogger(__name__)

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
NOT_DELIVERED = "org %s: %s was not delivered to %s: %s"

# Once, and once again on a connection error or a 5xx: an alert is said once a day, so a URL that
# is down for a minute is told twice and then the log holds it alone.
ATTEMPTS = 2
# A post waits this long for a 2xx.
WAITS_S = 5.0
EVENT_HEADER = "x-pinecall-event"
SIGNATURE_HEADER = "x-pinecall-signature"
A_SERVER_ERROR = 500
# The post a person asks for to prove their URL: posted, never kept.
A_TEST = "webhook.test"
A_TEST_SAYS = {"said": "Pinecall reaches this URL; every alert of the org comes the same way."}
# How many alerts one gateway takes to post at a time: their posts wait on their URLs together.
MOST_AT_ONCE = 20


@dataclass(frozen=True, slots=True)
class Webhook:
    """The URL alerts are posted to, the secret each post is signed with, and whether it is held to the internet."""

    url: str
    secret: str | None = None
    # An org's is: the box posts to it on the org's word. The operator's own may be inside the box's network.
    public: bool = True

    def __post_init__(self) -> None:
        if not self.url.startswith(("http://", "https://")):
            raise ValidationError(NOT_A_URL.format(said=self.url))

    @property
    def signed(self) -> bool:
        """Whether its posts carry a signature."""
        return self.secret is not None


@dataclass(frozen=True, slots=True)
class Delivery:
    """How one post that was waited for went: taken, or why not."""

    sent: bool
    error: str | None


@dataclass(frozen=True, slots=True)
class Post:
    """One alert taken to be posted: what is sent, and the webhooks that hear it."""

    org: str
    sent: JsonObject
    heard_by: tuple[Webhook, ...]


def _load_url(value: Mapping[str, Any]) -> str:
    return str(value["url"])


def _dump_url(url: str) -> dict[str, Any]:
    return {"url": url}


# The box setting the operator's URL is kept under; its secret sealed beside it.
OPERATOR_ALERTS: platform.Setting[str] = platform.Setting("alerts", _load_url, _dump_url)


# ── an org's own, and the operator's ──


async def webhook_of(session: AsyncSession, vault: Vault, org: str) -> Webhook | None:
    """Where the org's alerts go, secret opened; None when they go nowhere."""
    row = await WebhookRepository(session).find(org)
    if row is None:
        return None
    return Webhook(url=row.url, secret=vault.open(row.ciphertext) if row.ciphertext else None)


# The box posts to this URL on the org's word: one that resolves inside the box, the cluster or a
# private network would make it a way into them, so the host is resolved and held to the internet
# before the URL is kept, and again before every post (`_send`), which connects to the address
# this answered.
async def addresses_of(webhook: Webhook) -> tuple[dns.Address, ...]:
    """The public addresses the webhook's host resolves to now; refused when local, private or unresolved."""
    found = await dns.resolve_url(webhook.url)
    host = found.host
    if not host or host == "localhost" or host.endswith(dns.LOCAL_SUFFIXES):
        raise ValidationError(NOT_ON_THE_INTERNET.format(host=host or webhook.url))
    if not found.addresses:
        raise ValidationError(NOT_RESOLVED.format(host=host))
    if not found.is_public:
        raise ValidationError(NOT_ON_THE_INTERNET.format(host=host))
    return found.addresses


async def put_webhook(session: AsyncSession, vault: Vault, org: str, webhook: Webhook) -> None:
    """Keep where the org's alerts go, replacing what it had; a URL into the box is refused."""
    await addresses_of(webhook)
    ciphertext = None if webhook.secret is None else vault.seal(webhook.secret)
    await WebhookRepository(session).put(org, url=webhook.url, ciphertext=ciphertext)


async def delete_webhook(session: AsyncSession, org: str) -> None:
    """Forget where the org's alerts went; NotFound when they went nowhere."""
    if not await WebhookRepository(session).delete_of_org(org):
        raise NotFound(ALERTS_GO_NOWHERE)


# No foreign key reaches the row from its org (`org_webhooks.org` is text): the org's erasure calls this.
async def forget_webhook(session: AsyncSession, org: str) -> bool:
    """Forget the webhook of an org that is being erased; whether it had one."""
    return await WebhookRepository(session).delete_of_org(org)


# The operator reads every org's alerts as the org does, the same post: what breaks for a tenant
# is the box's to see, whether or not the tenant named a URL of its own.
async def operator_webhook_of(session: AsyncSession, vault: Vault) -> Webhook | None:
    """Where the operator hears every org's alerts, secret opened; None when nowhere."""
    sealed = await platform.find_sealed_setting(session, OPERATOR_ALERTS)
    if sealed is not None:
        url, ciphertext = sealed
        return Webhook(url=url, secret=vault.open(ciphertext), public=False)
    unsigned = await platform.find_setting(session, OPERATOR_ALERTS)
    return None if unsigned is None else Webhook(url=unsigned, public=False)


async def put_operator_webhook(session: AsyncSession, vault: Vault, webhook: Webhook) -> None:
    """Keep where the operator hears every org's alerts, replacing what the box had."""
    ciphertext = None if webhook.secret is None else vault.seal(webhook.secret)
    await platform.put_setting(session, OPERATOR_ALERTS, webhook.url, ciphertext=ciphertext)


async def delete_operator_webhook(session: AsyncSession) -> None:
    """Forget where the operator heard the alerts; NotFound when it heard them nowhere."""
    if not await platform.delete_setting(session, OPERATOR_ALERTS):
        raise NotFound(THE_OPERATOR_HEARS_NOTHING)


# ── the post ──


# Until 2026-11 an alert was posted as it was raised, inside the transaction of whoever raised it: the
# seal of a call, a turn of a chat. A slow URL of one tenant held a connection of the pool, and the
# monitor's row, for up to twenty seconds a call; and a transaction rolled back afterwards had posted
# an alert that no row kept. The alert's row is the outbox now: it is written with `posted_at` empty
# in the caller's transaction, and this pass, on every gateway, takes the rows that wait and posts them
# with no transaction open. A row is marked as it is taken, so no two gateways post it and none posts it
# twice; a gateway that dies between the two leaves that alert on the agent's log, in the mail and in
# the list, as a URL that was down always did.
async def post_pending(sessions: async_sessionmaker[AsyncSession], vault: Vault, http: httpx.AsyncClient) -> int:
    """Post every alert that waits for it to the webhooks that hear it; how many alerts were taken."""
    taken = 0
    posts = await _take_posts(sessions, vault)
    while posts:
        await asyncio.gather(*(_deliver(http, post) for post in posts))
        taken += len(posts)
        posts = await _take_posts(sessions, vault) if len(posts) == MOST_AT_ONCE else []
    return taken


async def _take_posts(sessions: async_sessionmaker[AsyncSession], vault: Vault) -> list[Post]:
    async with sessions.begin() as session:
        with box_wide():
            alerts = await AlertRepository(session).take_unposted(MOST_AT_ONCE, now())
            if not alerts:
                return []
            operators = await operator_webhook_of(session, vault)
            theirs = {org: await webhook_of(session, vault, org) for org in {alert.org for alert in alerts}}
    return [Post(alert.org, _payload_of(alert), _hearers_of(alert, theirs[alert.org], operators)) for alert in alerts]


# An alert that is the operators' alone is never posted to the org's webhook either.
def _hearers_of(alert: Alert, theirs: Webhook | None, operators: Webhook | None) -> tuple[Webhook, ...]:
    own = None if kinds.NAMED[alert.kind].operators_alone else theirs
    return tuple(webhook for webhook in (own, operators) if webhook is not None)


# A URL the client cannot even read is said, and the webhooks after it and the alerts beside it are
# posted all the same.
async def _deliver(http: httpx.AsyncClient, post: Post) -> None:
    for webhook in post.heard_by:
        with survive("posting an alert", webhook.url):
            error = await post_alert(http, webhook, post.sent)
            if error is not None:
                logger.warning(NOT_DELIVERED, post.org, post.sent["type"], webhook.url, error)


async def post_alert(http: httpx.AsyncClient, webhook: Webhook, sent: JsonObject) -> str | None:
    """Post the payload, again on a connection error or a 5xx; None on a 2xx, else why not."""
    body = json.dumps(sent, separators=(",", ":")).encode()
    headers = {"content-type": "application/json", EVENT_HEADER: str(sent["type"])}
    if webhook.secret is not None:
        digest = hmac.new(webhook.secret.encode(), body, hashlib.sha256).hexdigest()
        headers[SIGNATURE_HEADER] = f"sha256={digest}"
    error = "never posted"
    for _ in range(ATTEMPTS):
        try:
            answer = await _send(http, webhook, body, headers)
        except ValidationError as inside:
            return str(inside)
        except httpx.HTTPError as unreachable:
            error = f"{type(unreachable).__name__}: {unreachable}"
            continue
        if answer.is_success:
            return None
        error = f"HTTP {answer.status_code}"
        if answer.status_code < A_SERVER_ERROR:
            return error
    return error


# Until 2026-11 the host was held to the internet once, as the URL was kept, and every post resolved
# it again: a name that answered a public address that day and a private one later (DNS rebinding)
# had the gateway post inside the cluster. An org's URL is resolved and checked before every post,
# and the post connects to the address that was checked, never to the name again (`dns.post_at`).
# The client follows no redirect.
async def _send(http: httpx.AsyncClient, webhook: Webhook, body: bytes, headers: dict[str, str]) -> httpx.Response:
    if not webhook.public:
        return await http.post(webhook.url, content=body, headers=headers, timeout=WAITS_S)
    address = (await addresses_of(webhook))[0]
    return await dns.post_at(http, webhook.url, address, content=body, headers=headers, timeout=WAITS_S)


def _payload_of(alert: Alert) -> JsonObject:
    return _payload(Scope(alert.org, alert.env), alert.agent, alert.kind.value, alert.at.timestamp(), alert.data)


def _payload(scope: Scope, agent: str | None, kind: str, at: float, data: JsonObject) -> JsonObject:
    """What a post carries: the kind, whose env it is, the agent, when, and the alert itself."""
    return {"type": kind, "org": scope.org, "env": scope.env, "agent": agent, "at": at, "data": data}


# ── the test ──


# The one post a person waits for: they watch whether their URL answered. The webhook is read in a
# transaction that is over before the URL is asked, so the request holds no connection while it waits.
async def test_webhook(
    sessions: async_sessionmaker[AsyncSession], vault: Vault, http: httpx.AsyncClient, scope: Scope
) -> Delivery:
    """One test post to the org's webhook, signed as every alert is, waited for; NotFound when the org set none."""
    async with sessions() as session:
        found = await webhook_of(session, vault, scope.org)
    if found is None:
        raise NotFound(ALERTS_GO_NOWHERE)
    error = await post_alert(http, found, _payload(scope, None, A_TEST, epoch(), dict(A_TEST_SAYS)))
    return Delivery(sent=error is None, error=error)
