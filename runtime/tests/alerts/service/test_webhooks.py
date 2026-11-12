"""Where an org's alerts go: the URL it may name, who hears a kept alert, and what each post carries."""

import hashlib
import hmac
import json

import httpx
import pytest

from runtime.alerts.models import Alert, AlertKind
from runtime.alerts.service.webhooks import ATTEMPTS, Webhook, addresses_of, post_alert, post_of
from runtime.enums import Env
from runtime.exceptions import ValidationError
from runtime.kit.time import now
from runtime.wire.base import WireModel
from runtime.wire.feed import OrgQuiet
from tests.alerts.factories import A_FAILED_APP
from tests.fakes.webhooks import Receiver

SHH = "shh"
ORG = "org_1"
# An address of the internet, so no name is asked of a resolver.
THE_ORGS = Webhook("https://93.184.216.34/hooks/x")
THE_OPERATORS = Webhook("https://hooks.example.test/alerts?the-operator", "ops-secret", public=False)


def kept(kind: AlertKind, alert: WireModel, *, agent: str | None = None) -> Alert:
    """The alert as its row holds it, raised in the org's sandbox."""
    return Alert(
        id="alr_1",
        org=ORG,
        env=Env.sandbox,
        agent=agent,
        kind=kind,
        subject="",
        data=alert.dump(),
        mailed=False,
        at=now(),
        posted_at=None,
    )


def test_a_webhook_is_an_http_url_with_or_without_a_secret() -> None:
    assert Webhook("https://hooks.example.test/alerts").secret is None
    assert Webhook("http://localhost:8080/", SHH).secret == SHH
    with pytest.raises(ValidationError, match="http\\(s\\) URL"):
        Webhook("hooks.example.test/alerts")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9/x",
        "http://localhost:8080/",
        "https://10.0.0.5/hooks",
        "http://169.254.169.254/latest/meta-data",
        "https://alerts.internal/post",
        "https://[::1]/",
    ],
)
async def test_a_webhook_into_the_box_or_a_private_network_is_refused(url: str) -> None:
    """The box posts on the org's word: a host that is local, private or link-local is refused by name."""
    with pytest.raises(ValidationError, match="posted to the public internet"):
        await addresses_of(Webhook(url))


async def test_a_webhook_on_the_public_internet_is_kept_with_the_address_it_is_posted_at() -> None:
    (address,) = await addresses_of(THE_ORGS)
    assert str(address) == "93.184.216.34"


def test_a_kept_alert_is_heard_by_the_orgs_webhook_and_the_operators_and_says_whose_it_is() -> None:
    row = kept(AlertKind.app_failed, A_FAILED_APP)
    post = post_of(row, THE_ORGS, THE_OPERATORS)
    assert post.heard_by == (THE_ORGS, THE_OPERATORS)
    assert post.sent == {
        "type": "app.failed",
        "org": ORG,
        "env": "sandbox",
        "agent": None,
        "at": row.at.timestamp(),
        "data": A_FAILED_APP.dump(),
    }
    assert post_of(row, None, THE_OPERATORS).heard_by == (THE_OPERATORS,)
    assert post_of(row, None, None).heard_by == ()


def test_an_alert_that_is_the_operators_alone_never_reaches_the_orgs_webhook() -> None:
    quiet = OrgQuiet(org=ORG, name="ClickBoss", created_at=1793805000.0, calls=3, failed=2)
    assert post_of(kept(AlertKind.org_quiet, quiet), THE_ORGS, THE_OPERATORS).heard_by == (THE_OPERATORS,)


async def test_a_post_is_signed_with_the_webhooks_secret_and_sent_at_the_address_checked() -> None:
    """The operator's is signed with its secret; the org's, with none, carries no signature and its own host."""
    receiver = Receiver()
    post = post_of(kept(AlertKind.app_failed, A_FAILED_APP), THE_ORGS, THE_OPERATORS)
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver.answer)) as http:
        for webhook in post.heard_by:
            assert await post_alert(http, webhook, post.sent) is None
    to_the_org, to_the_operator = receiver.heard
    assert json.loads(to_the_org.content) == json.loads(to_the_operator.content) == json.loads(json.dumps(post.sent))
    assert to_the_org.headers["x-pinecall-event"] == "app.failed"
    assert "x-pinecall-signature" not in to_the_org.headers
    assert (to_the_org.url.host, to_the_org.headers["host"]) == ("93.184.216.34", "93.184.216.34")
    signature = hmac.new(b"ops-secret", to_the_operator.content, hashlib.sha256).hexdigest()
    assert to_the_operator.headers["x-pinecall-signature"] == f"sha256={signature}"
    assert str(to_the_operator.url) == THE_OPERATORS.url


async def test_a_url_that_is_down_is_told_twice_and_one_that_refuses_once() -> None:
    post = post_of(kept(AlertKind.app_failed, A_FAILED_APP), THE_ORGS, None)
    down, refusing = Receiver(answers=[503]), Receiver(answers=[410])
    async with httpx.AsyncClient(transport=httpx.MockTransport(down.answer)) as http:
        assert await post_alert(http, THE_ORGS, post.sent) == "HTTP 503"
    async with httpx.AsyncClient(transport=httpx.MockTransport(refusing.answer)) as http:
        assert await post_alert(http, THE_ORGS, post.sent) == "HTTP 410"
    assert (len(down.heard), len(refusing.heard)) == (ATTEMPTS, 1)


async def test_an_orgs_url_that_points_inside_is_never_posted_to() -> None:
    """Held to the internet again before every post: a URL kept while public and private since is refused, unposted."""
    receiver = Receiver()
    post = post_of(kept(AlertKind.app_failed, A_FAILED_APP), THE_ORGS, None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver.answer)) as http:
        refused = await post_alert(http, Webhook("https://10.0.0.5/hooks"), post.sent)
    assert refused is not None and "posted to the public internet" in refused
    assert receiver.heard == []
