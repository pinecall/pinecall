"""Mailboxes: an SMTP account, the org's own, the box's, and how the last email through each went."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.exceptions import ValidationError
from runtime.kit.crypto import Vault
from runtime.kit.text import AN_EMAIL
from runtime.kit.time import now
from runtime.mail.repository import MailRepository
from runtime.platform import service as platform

type Security = Literal["starttls", "tls", "none"]
# The org's own, the box's the operator stored, or the box's the environment names.
type Source = Literal["org", "stored", "environment"]

A_HOST = re.compile(r"^[A-Za-z0-9.\-_\[\]:]+$")
HIGHEST_PORT = 65535
TIMEOUT_S = 10.0
SCHEMES: dict[str, tuple[int, Security]] = {"smtp": (587, "starttls"), "smtps": (465, "tls")}


@dataclass(frozen=True, slots=True)
class Mailbox:
    """An SMTP account: the server, the credentials, and who the emails are from."""

    host: str
    port: int
    security: Security
    username: str
    password: str
    sender: str

    def __post_init__(self) -> None:
        if not A_HOST.match(self.host):
            raise ValidationError(f"{self.host!r} is not a host: a mail server is named bare")
        if not 1 <= self.port <= HIGHEST_PORT:
            raise ValidationError(f"a port is 1 to {HIGHEST_PORT}, not {self.port}")
        address_of(self.sender)


@dataclass(frozen=True, slots=True)
class MailboxStatus:
    """A mailbox, where it was read from, and how its last email went."""

    mailbox: Mailbox
    source: Source
    verified_at: datetime | None = None
    last_error: str | None = None

    # Flat, as the page that shows a mailbox reads it; never the password.
    configured = True

    @property
    def host(self) -> str:
        """The mail server."""
        return self.mailbox.host

    @property
    def port(self) -> int:
        """Its port."""
        return self.mailbox.port

    @property
    def security(self) -> Security:
        """How the connection is secured."""
        return self.mailbox.security

    @property
    def username(self) -> str:
        """The account's name."""
        return self.mailbox.username

    @property
    def sender(self) -> str:
        """Who the emails are from."""
        return self.mailbox.sender


def address_of(written: str) -> str:
    """The address in `Name <a@b.c>` or a bare one; refused when there is none."""
    _, address = parseaddr(written)
    if not AN_EMAIL.match(address):
        raise ValidationError(f"{written!r} carries no email address")
    return address


# Split at the LAST `@`: an SES password is base64 and may hold a raw `/`.
def parse_mailbox_url(url: str, sender: str) -> Mailbox:
    """`smtp://user:pass@host:587` or `smtps://…`, and who emails are from, as a mailbox."""
    scheme, separated, rest = url.strip().partition("://")
    if not separated or scheme not in SCHEMES:
        raise ValidationError("a mail URL starts smtp:// (STARTTLS) or smtps:// (implicit TLS)")
    port, security = SCHEMES[scheme]
    userinfo, _, where = rest.rpartition("@")
    parts = urlsplit(f"{scheme}://{where.split('/', 1)[0]}")
    if not parts.hostname:
        raise ValidationError("the mail URL names no mail server after its `@`")
    try:
        named = parts.port
    except ValueError:
        raise ValidationError("the mail URL's port is not a number") from None
    username, _, password = userinfo.partition(":")
    return Mailbox(parts.hostname, named or port, security, unquote(username), unquote(password), sender)


def _security(word: str) -> Security:
    match word:
        case "starttls" | "tls" | "none":
            return word
        case _:
            raise ValidationError(f"a mailbox is secured by starttls, tls or none, not {word!r}")


async def find_org_mailbox(session: AsyncSession, vault: Vault, org: str) -> MailboxStatus | None:
    """The org's own mailbox and how its last email went; None when it has none."""
    row = await MailRepository(session).find(org)
    if row is None:
        return None
    mailbox = Mailbox(row.host, row.port, _security(row.security), row.username, vault.open(row.ciphertext), row.sender)
    return MailboxStatus(mailbox, "org", row.verified_at, row.last_error)


async def put_org_mailbox(session: AsyncSession, vault: Vault, org: str, mailbox: Mailbox) -> None:
    """Keep the org's own mailbox, the password sealed; how it went is forgotten."""
    if mailbox.security == "none":
        raise ValidationError(
            "an org's mailbox is reached over TLS, starttls or tls: none is the box's own relay alone"
        )
    values: dict[str, Any] = {
        "host": mailbox.host,
        "port": mailbox.port,
        "security": mailbox.security,
        "username": mailbox.username,
        "ciphertext": vault.seal(mailbox.password),
        "sender": mailbox.sender,
        "verified_at": None,
        "last_error": None,
        "set_at": now(),
    }
    await MailRepository(session).put(org, values)


async def delete_org_mailbox(session: AsyncSession, org: str) -> bool:
    """Forget the org's own mailbox; whether it had one."""
    repository = MailRepository(session)
    row = await repository.find(org)
    if row is None:
        return False
    await repository.delete(row)
    return True


# Kept on the mailbox the email went through, so the page that shows the mailbox says how it went.
async def record_org_delivery(session: AsyncSession, org: str, error: str | None) -> None:
    """Keep how the last email through the org's mailbox went: when it was taken, or what refused it."""
    repository = MailRepository(session)
    row = await repository.find(org)
    if row is None:
        return
    values: dict[str, Any] = {"last_error": error}
    if error is None:
        values["verified_at"] = now()
    await repository.update(row, **values)


@dataclass(frozen=True, slots=True)
class StoredMailbox:
    """The mailbox the operator stored for the box, without its password, and how its last email went."""

    host: str
    port: int
    security: Security
    username: str
    sender: str
    verified_at: datetime | None = None
    last_error: str | None = None


def _load_stored(value: Mapping[str, Any]) -> StoredMailbox:
    verified = value.get("verified_at")
    failed = value.get("last_error")
    return StoredMailbox(
        host=str(value["host"]),
        port=int(value["port"]),
        security=_security(str(value["security"])),
        username=str(value.get("username") or ""),
        sender=str(value["sender"]),
        verified_at=None if verified is None else datetime.fromisoformat(str(verified)),
        last_error=None if failed is None else str(failed),
    )


def _dump_stored(stored: StoredMailbox) -> dict[str, Any]:
    kept: dict[str, Any] = {
        "host": stored.host,
        "port": stored.port,
        "security": stored.security,
        "username": stored.username,
        "sender": stored.sender,
    }
    if stored.verified_at is not None:
        kept["verified_at"] = stored.verified_at.isoformat()
    if stored.last_error is not None:
        kept["last_error"] = stored.last_error
    return kept


# The box_settings row the operator's stored mailbox is kept in, its password sealed beside it.
BOX_MAIL: platform.Setting[StoredMailbox] = platform.Setting("mail", _load_stored, _dump_stored)


async def find_box_mailbox(session: AsyncSession, vault: Vault, environment: Mailbox | None) -> MailboxStatus | None:
    """The box's mailbox: the one the operator stored, else the environment's; None when it has neither."""
    kept = await platform.find_sealed_setting(session, BOX_MAIL)
    if kept is None:
        return None if environment is None else MailboxStatus(environment, "environment")
    stored, sealed = kept
    mailbox = Mailbox(stored.host, stored.port, stored.security, stored.username, vault.open(sealed), stored.sender)
    return MailboxStatus(mailbox, "stored", stored.verified_at, stored.last_error)


async def put_box_mailbox(session: AsyncSession, vault: Vault, mailbox: Mailbox) -> None:
    """Keep the mailbox the box sends through, over the environment's; how it went is forgotten."""
    stored = StoredMailbox(mailbox.host, mailbox.port, mailbox.security, mailbox.username, mailbox.sender)
    await platform.put_setting(session, BOX_MAIL, stored, ciphertext=vault.seal(mailbox.password))


async def delete_box_mailbox(session: AsyncSession) -> bool:
    """Forget the box's stored mailbox, back to the environment's; whether one was stored."""
    return await platform.delete_setting(session, BOX_MAIL)


async def record_box_delivery(session: AsyncSession, error: str | None) -> None:
    """Keep how the last email through the box's stored mailbox went."""
    kept = await platform.find_sealed_setting(session, BOX_MAIL)
    if kept is None:
        return
    stored, sealed = kept
    went = StoredMailbox(
        stored.host,
        stored.port,
        stored.security,
        stored.username,
        stored.sender,
        verified_at=now() if error is None else stored.verified_at,
        last_error=error,
    )
    await platform.put_setting(session, BOX_MAIL, went, ciphertext=sealed)


def read_environment_mailbox(smtp_url: str | None, sender: str | None) -> Mailbox | None:
    """The mailbox the environment names (`PINECALL_SMTP_URL`, `PINECALL_MAIL_FROM`); None when it names none."""
    return None if smtp_url is None else parse_mailbox_url(smtp_url, sender or "")
