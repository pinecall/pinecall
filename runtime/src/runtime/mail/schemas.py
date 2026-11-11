"""The bodies of the mail endpoints: a mailbox written and shown, a test email asked for and answered."""

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import Field

from runtime.kit.schemas import Row, Schema


class PutMail(Schema):
    """PUT /v1/org/mail and /v1/ops/mail: an SMTP account, its password included every time."""

    host: str
    port: int
    security: Literal["starttls", "tls", "none"] = "starttls"
    username: str = ""
    password: str = ""
    sender: str = Field(alias="from")

    def fields(self) -> dict[str, Any]:
        """The account's fields by name, the words trimmed and the password as typed."""
        return {
            "host": self.host.strip(),
            "port": self.port,
            "security": self.security,
            "username": self.username.strip(),
            "password": self.password,
            "sender": self.sender.strip(),
        }


class MailRow(Row):
    """GET /v1/org/mail: the mailbox, never its password, and how its last email went."""

    configured: bool
    host: str | None = None
    port: int | None = None
    security: str | None = None
    username: str | None = None
    sender: str | None = Field(default=None, alias="from", serialization_alias="from")
    verified_at: datetime | None = None
    last_error: str | None = None

    @classmethod
    def of_mailbox(cls, kept: object | None) -> Self:
        """The row of a mailbox and how it went, or of none."""
        return cls(configured=False) if kept is None else cls.model_validate(kept)


class BoxMailRow(MailRow):
    """GET and PUT /v1/ops/mail: the box's mailbox and where it came from, never the password."""

    source: Literal["stored", "environment"] | None = None


class SendTestEmail(Schema):
    """POST /v1/org/mail/test and /v1/ops/mail/test."""

    to: str


class TestEmailSent(Row):
    """The answer to a test email: whether it went, and what the server said when not."""

    sent: bool
    error: str | None
