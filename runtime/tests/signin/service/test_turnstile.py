"""Turnstile: no secret passes everything; with one, only Cloudflare's yes for this action on this box opens."""

from dataclasses import dataclass, field

import httpx
import pytest

from runtime.exceptions import Forbidden
from runtime.signin.service.turnstile import SITEVERIFY, Turnstile

A_TOKEN = "0.solved-by-a-browser"


@dataclass
class Cloudflare:
    """Cloudflare's siteverify, answering what the test tells it; None does not answer at all."""

    says: dict[str, object] | None = None
    asked: list[httpx.Request] = field(default_factory=list[httpx.Request])

    def answer(self, request: httpx.Request) -> httpx.Response:
        """What it was told to say, at siteverify alone."""
        self.asked.append(request)
        assert str(request.url) == SITEVERIFY
        if self.says is None:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, json=self.says)

    def verifier(self, secret: str | None = "a-secret", hostname: str | None = "voice.example.com") -> Turnstile:
        """A verifier the operator gave this secret, on a box with that name, reaching this Cloudflare."""
        return Turnstile(httpx.AsyncClient(transport=httpx.MockTransport(self.answer)), secret, hostname)


async def test_a_box_with_no_turnstile_asks_for_no_token() -> None:
    """Without a secret every request passes, token or not, and Cloudflare is never asked."""
    cloudflare = Cloudflare()
    await cloudflare.verifier(secret=None).check(None, "signup", "203.0.113.9")
    assert not cloudflare.asked


async def test_a_missing_token_is_refused_before_cloudflare_is_asked() -> None:
    """With a secret, a request carrying no token is refused without a round trip."""
    cloudflare = Cloudflare()
    with pytest.raises(Forbidden, match="captcha"):
        await cloudflare.verifier().check(None, "signup", "203.0.113.9")
    assert not cloudflare.asked


async def test_cloudflares_yes_for_this_action_on_this_box_passes() -> None:
    """A token Cloudflare says was solved for this action on the box's page opens the door."""
    cloudflare = Cloudflare({"success": True, "action": "signup", "hostname": "voice.example.com"})
    await cloudflare.verifier().check(A_TOKEN, "signup", "203.0.113.9")
    sent = cloudflare.asked[-1].content.decode()
    assert "secret=a-secret" in sent and f"response={A_TOKEN}" in sent and "remoteip=203.0.113.9" in sent


async def test_a_token_solved_for_another_door_is_refused() -> None:
    """A sign-up's token does not mail a code again: the action Cloudflare answers must be this door's."""
    cloudflare = Cloudflare({"success": True, "action": "signup", "hostname": "voice.example.com"})
    with pytest.raises(Forbidden, match="captcha"):
        await cloudflare.verifier().check(A_TOKEN, "signup_resend", "203.0.113.9")


async def test_a_token_solved_on_another_page_is_refused() -> None:
    """Where the box has a name, a token solved elsewhere is refused; a box with none cannot tell."""
    cloudflare = Cloudflare({"success": True, "action": "signup", "hostname": "evil.example.net"})
    with pytest.raises(Forbidden, match="captcha"):
        await cloudflare.verifier().check(A_TOKEN, "signup", "203.0.113.9")
    await cloudflare.verifier(hostname=None).check(A_TOKEN, "signup", "203.0.113.9")


async def test_cloudflare_saying_no_or_nothing_refuses() -> None:
    """A failed verification, and Cloudflare not answering at all, both refuse: a shield that is down is no shield."""
    cloudflare = Cloudflare({"success": False, "error-codes": ["invalid-input-response"]})
    with pytest.raises(Forbidden, match="captcha"):
        await cloudflare.verifier().check(A_TOKEN, "signup", "203.0.113.9")
    cloudflare.says = None
    with pytest.raises(Forbidden, match="captcha"):
        await cloudflare.verifier().check(A_TOKEN, "signup", "203.0.113.9")
