"""Tests for where an org's alerts go."""

import pytest

from pinecall_runtime.alerts.service.webhooks import Webhook, check_reaches_the_internet
from pinecall_runtime.exceptions import ValidationError

SHH = "shh"


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
        await check_reaches_the_internet(Webhook(url))


async def test_a_webhook_on_the_public_internet_is_kept() -> None:
    await check_reaches_the_internet(Webhook("https://93.184.216.34/hooks/x"))
