"""A mail relay on this machine: every email handed to it over SMTP, kept as it arrived."""

import asyncio
from email import message_from_bytes, policy
from email.message import EmailMessage
from types import TracebackType
from typing import Self

from runtime.mail.service.mailboxes import Mailbox

SENDER = "alerts@box.test"
THE_END_OF_AN_EMAIL = b"\r\n.\r\n"


# What a box's own mailbox is where its relay sits beside it: plain SMTP on a private address, no
# account. The outbox reaches it as it reaches any mail server, so a test reads the email as sent.
class Relay:
    """The box's mail server for a test: an `Outbox` given its `mailbox` sends here."""

    def __init__(self) -> None:
        self.taken: list[EmailMessage] = []
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> Self:
        self._server = await asyncio.start_server(self._take, "127.0.0.1", 0)
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, raised: BaseException | None, trace: TracebackType | None
    ) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def mailbox(self) -> Mailbox:
        """The account an outbox sends through to reach this relay."""
        if self._server is None:
            raise RuntimeError("the relay is not listening")
        port = self._server.sockets[0].getsockname()[1]
        return Mailbox(host="127.0.0.1", port=port, security="none", username="", password="", sender=SENDER)

    def to(self, address: str) -> list[EmailMessage]:
        """The emails taken for one address, oldest first."""
        return [email for email in self.taken if email["To"] == address]

    async def _take(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async def say(line: bytes) -> None:
            writer.write(line + b"\r\n")
            await writer.drain()

        await say(b"220 relay.test")
        while line := await reader.readline():
            verb = line[:4].upper()
            if verb == b"DATA":
                await say(b"354 end with a dot on a line of its own")
                sent = await reader.readuntil(THE_END_OF_AN_EMAIL)
                # A line that opens with a dot travels with one more (RFC 5321 §4.5.2).
                body = sent.removesuffix(THE_END_OF_AN_EMAIL).replace(b"\r\n..", b"\r\n.")
                self.taken.append(message_from_bytes(body, policy=policy.default))
                await say(b"250 taken")
            elif verb == b"QUIT":
                await say(b"221 bye")
                break
            else:
                await say(b"250 ok")
        writer.close()
        await writer.wait_closed()


def text_of(email: EmailMessage) -> str:
    """The email's plain text, as a person without HTML reads it."""
    plain = email.get_body(("plain",))
    return "" if plain is None else str(plain.get_content())
