"""Turnstile: no secret passes everything; with one, only Cloudflare's yes for this action on this box opens."""

from collections.abc import Iterator

import httpx
import pytest
import respx

from pinecall_runtime.accounts.service.turnstile import SITEVERIFY, Turnstile
from pinecall_runtime.exceptions import Forbidden

A_TOKEN = "0.solved-by-a-browser"


@pytest.fixture
def cloudflare() -> Iterator[respx.MockRouter]:
    """Cloudflare's siteverify, faked."""
    with respx.mock(assert_all_called=False) as router:
        yield router


async def with_secret(hostname: str | None = "voice.example.com") -> Turnstile:
    """A verifier the operator gave a secret, on a box with that name."""
    return Turnstile(httpx.AsyncClient(), "a-secret", hostname)


async def test_a_box_with_no_turnstile_asks_for_no_token(cloudflare: respx.MockRouter) -> None:
    """Without a secret every request passes, token or not, and Cloudflare is never asked."""
    await Turnstile(httpx.AsyncClient(), None, "voice.example.com").check(None, "login", "203.0.113.9")
    assert not cloudflare.calls


async def test_a_missing_token_is_refused_before_cloudflare_is_asked(cloudflare: respx.MockRouter) -> None:
    """With a secret, a request carrying no token is refused without a round trip."""
    with pytest.raises(Forbidden, match="captcha"):
        await (await with_secret()).check(None, "login", "203.0.113.9")
    assert not cloudflare.calls


async def test_cloudflares_yes_for_this_action_on_this_box_passes(cloudflare: respx.MockRouter) -> None:
    """A token Cloudflare says was solved for this action on the box's page opens the door."""
    asked = cloudflare.post(SITEVERIFY).respond(
        json={"success": True, "action": "signup", "hostname": "voice.example.com"}
    )
    await (await with_secret()).check(A_TOKEN, "signup", "203.0.113.9")
    sent = asked.calls.last.request.content.decode()
    assert "secret=a-secret" in sent and f"response={A_TOKEN}" in sent and "remoteip=203.0.113.9" in sent


async def test_a_token_solved_for_another_door_is_refused(cloudflare: respx.MockRouter) -> None:
    """A login's token does not open a sign-up: the action Cloudflare answers must be this door's."""
    cloudflare.post(SITEVERIFY).respond(json={"success": True, "action": "login", "hostname": "voice.example.com"})
    with pytest.raises(Forbidden, match="captcha"):
        await (await with_secret()).check(A_TOKEN, "signup", "203.0.113.9")


async def test_a_token_solved_on_another_page_is_refused(cloudflare: respx.MockRouter) -> None:
    """Where the box has a name, a token solved elsewhere is refused; a box with none cannot tell."""
    cloudflare.post(SITEVERIFY).respond(json={"success": True, "action": "login", "hostname": "evil.example.net"})
    with pytest.raises(Forbidden, match="captcha"):
        await (await with_secret()).check(A_TOKEN, "login", "203.0.113.9")
    await (await with_secret(hostname=None)).check(A_TOKEN, "login", "203.0.113.9")


async def test_cloudflare_saying_no_or_nothing_refuses(cloudflare: respx.MockRouter) -> None:
    """A failed verification, and Cloudflare not answering at all, both refuse: a shield that is down is no shield."""
    cloudflare.post(SITEVERIFY).respond(json={"success": False, "error-codes": ["invalid-input-response"]})
    with pytest.raises(Forbidden, match="captcha"):
        await (await with_secret()).check(A_TOKEN, "login", "203.0.113.9")
    cloudflare.post(SITEVERIFY).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(Forbidden, match="captcha"):
        await (await with_secret()).check(A_TOKEN, "login", "203.0.113.9")
