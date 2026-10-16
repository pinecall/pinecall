"""Tests for where an org's alerts go."""

import pytest

from pinecall_runtime.alerts.service.webhooks import Webhook
from pinecall_runtime.exceptions import ValidationError

SHH = "shh"


def test_a_webhook_is_an_http_url_with_or_without_a_secret() -> None:
    assert Webhook("https://hooks.example.test/alerts").secret is None
    assert Webhook("http://localhost:8080/", SHH).secret == SHH
    with pytest.raises(ValidationError, match="http\\(s\\) URL"):
        Webhook("hooks.example.test/alerts")
