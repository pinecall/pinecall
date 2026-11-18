"""Meta's Graph API on a fake transport, and the one transport for everything outside the box."""

import hashlib
import hmac
import json
from dataclasses import dataclass, field

import httpx

from tests.fakes.twilio import Twilio
from tests.fakes.webhooks import HOST, Receiver

# Where Meta's Graph says a media's bytes are.
MEDIA_HOST = "lookaside.fbsbx.com"


@dataclass
class Graph:
    """Meta's Graph API on a fake transport: every message sent, or a refusal."""

    sent: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    tokens: list[str] = field(default_factory=list[str])
    # The messages marked read, each with whether "typing…" was asked for with it.
    read: list[tuple[str, bool]] = field(default_factory=list[tuple[str, bool]])
    # The audio Meta keeps, by media id: its bytes and their type.
    media: dict[str, tuple[bytes, str]] = field(default_factory=dict[str, tuple[bytes, str]])
    # How Graph answers a send it refuses; None sends.
    refusal: tuple[int, str] | None = None

    # The number the fake account answers at, as Meta shows it.
    number: str = "+598 29 001 199"
    name: str = "Clinica"

    def answer(self, request: httpx.Request) -> httpx.Response:
        """A send to a number's messages, kept, or refused as told; the account's number on GET."""
        named = request.url.path.split("/")[-1]
        if request.url.host == MEDIA_HOST:
            data, mime_type = self.media[named]
            return httpx.Response(200, content=data, headers={"content-type": mime_type})
        if request.method == "GET" and named in self.media:
            data, mime_type = self.media[named]
            kept = {"url": f"https://{MEDIA_HOST}/whatsapp/{named}", "mime_type": mime_type, "file_size": len(data)}
            return httpx.Response(200, json={**kept, "id": named})
        if request.method == "GET":
            if self.refusal is not None:
                status, text = self.refusal
                return httpx.Response(status, json={"error": {"message": text, "code": 190}})
            text = {"display_phone_number": self.number, "verified_name": self.name}
            return httpx.Response(200, json={**text, "id": request.url.path.split("/")[2]})
        if self.refusal is not None:
            status, text = self.refusal
            return httpx.Response(status, json={"error": {"message": text, "code": 131047}})
        self.tokens.append(request.headers.get("authorization", ""))
        body: dict[str, object] = json.loads(request.content)
        if body.get("status") == "read":
            self.read.append((str(body.get("message_id")), "typing_indicator" in body))
            return httpx.Response(200, json={"success": True})
        self.sent.append({"from": request.url.path.split("/")[2], **body})
        return httpx.Response(200, json={"messages": [{"id": f"wamid.{len(self.sent)}"}]})


def outside(twilio: Twilio, graph: Graph, receiver: Receiver) -> httpx.MockTransport:
    """One transport for everything outside the box: Graph, a webhook, Twilio for the rest."""

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.host in ("graph.facebook.com", MEDIA_HOST):
            return graph.answer(request)
        if request.url.host == HOST:
            return receiver.answer(request)
        return twilio.transport().handle_request(request)

    return httpx.MockTransport(answer)


# ── what Meta delivers ──

SIGNING = "the app's own secret"
OUR_NUMBER = "+59829001199"


def signed(body: bytes, secret: str = SIGNING) -> str:
    """The header Meta sends with a body."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def a_body(
    *messages: dict[str, object], contacts: list[dict[str, object]] | None = None, phone_number_id: str = "1055"
) -> bytes:
    """Meta's envelope around these messages, to the box's number."""
    value: dict[str, object] = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": OUR_NUMBER.lstrip("+"), "phone_number_id": phone_number_id},
        "contacts": contacts if contacts is not None else [{"wa_id": "59899000001", "profile": {"name": "Ana"}}],
        "messages": list(messages),
    }
    return json.dumps({"entry": [{"id": "waba", "changes": [{"field": "messages", "value": value}]}]}).encode()


def a_text(text: str, sender: str = "59899000001", message: str = "wamid.1") -> dict[str, object]:
    """One text message as Meta writes it."""
    return {"from": sender, "id": message, "type": "text", "text": {"body": text}, "timestamp": "1"}
