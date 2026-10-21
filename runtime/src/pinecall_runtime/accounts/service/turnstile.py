"""Cloudflare Turnstile: the proof a stranger's browser gives before a door costs the box anything."""

import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from pinecall_runtime.exceptions import Forbidden

log = logging.getLogger(__name__)

SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
# Cloudflare's tokens are far shorter; a longer one is not a token.
LONGEST_TOKEN = 2048
# Each door sends its own action and Cloudflare answers it back, so a token solved for one door
# does not open another (Cloudflare: 32 characters of letters, digits, `_` and `-`).
type Action = Literal["login", "signup", "signup_resend", "password_reset"]
REFUSED = "the captcha was not passed: complete it and try again"


@dataclass(frozen=True)
class Turnstile:
    """The verifier: with no secret every token passes, as a box with no Turnstile asks for none."""

    http: httpx.AsyncClient
    secret: str | None
    # The box's name where it has one: a token solved on another page is refused.
    hostname: str | None

    async def check(self, token: str | None, action: Action, client: str) -> None:
        """Refuse unless Cloudflare says the token was solved for this action on this box's page."""
        if self.secret is None:
            return
        if not token or len(token) > LONGEST_TOKEN:
            log.warning("turnstile: %s from %s carried no token", action, client)
            raise Forbidden(REFUSED)
        asked = {"secret": self.secret, "response": token, "remoteip": client}
        try:
            answer = await self.http.post(SITEVERIFY, data=asked, timeout=10.0)
            answer.raise_for_status()
            said = answer.json()
        except (httpx.HTTPError, ValueError) as failed:
            # Cloudflare not answering refuses too: a door that opens when the shield is down is no shield.
            log.warning("turnstile: siteverify did not answer for %s: %s", action, failed)
            raise Forbidden(REFUSED) from None
        if said.get("success") is not True or said.get("action") != action:
            log.warning("turnstile: token refused for %s: %s", action, said.get("error-codes", said.get("action")))
            raise Forbidden(REFUSED)
        if self.hostname is not None and str(said.get("hostname", "")).lower() != self.hostname:
            log.warning("turnstile: token for %s solved on %r, not this box", action, said.get("hostname"))
            raise Forbidden(REFUSED)
