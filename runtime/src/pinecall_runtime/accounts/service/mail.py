"""Mailboxes: the org's own, the box's, and the outbox that posts an email in the background."""

import asyncio
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Literal
from urllib.parse import unquote, urlsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.accounts.models import OrgMail
from pinecall_runtime.accounts.repository import MailRepository
from pinecall_runtime.accounts.service.emails import Email
from pinecall_runtime.exceptions import UpstreamError, ValidationError
from pinecall_runtime.kit import dns
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.kit.text import AN_EMAIL
from pinecall_runtime.kit.time import now
from pinecall_runtime.platform import service as platform

logger = logging.getLogger(__name__)

type Security = Literal["starttls", "tls", "none"]
# The org's own, the box's the operator stored, or the box's the environment names.
type Source = Literal["org", "stored", "environment"]

A_HOST = re.compile(r"^[A-Za-z0-9.\-_\[\]:]+$")
HIGHEST_PORT = 65535
TIMEOUT_S = 10.0
SCHEMES: dict[str, tuple[int, Security]] = {"smtp": (587, "starttls"), "smtps": (465, "tls")}
# The box_settings row the operator's stored mailbox is kept in, its password sealed beside it.
BOX_MAIL = "mail"


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


async def get_org_mailbox(session: AsyncSession, vault: Vault, org: str) -> MailboxStatus | None:
    """The org's own mailbox and how its last email went."""
    row = await MailRepository(session).get(org)
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
    repository = MailRepository(session)
    row = await repository.get(org)
    values = {
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
    if row is None:
        await repository.add(OrgMail(org=org, **values))
    else:
        await repository.update(row, **values)


async def get_box_mailbox(session: AsyncSession, vault: Vault, environment: Mailbox | None) -> MailboxStatus | None:
    """The box's mailbox: the one the operator stored, else the environment's."""
    kept = await platform.get_sealed_setting(session, BOX_MAIL)
    if kept is not None:
        value, sealed = kept
        mailbox = Mailbox(
            str(value["host"]),
            int(value["port"]),
            _security(str(value["security"])),
            str(value.get("username") or ""),
            vault.open(sealed),
            str(value["sender"]),
        )
        verified = value.get("verified_at")
        verified_at = None if verified is None else datetime.fromisoformat(str(verified))
        last_error = value.get("last_error")
        return MailboxStatus(mailbox, "stored", verified_at, None if last_error is None else str(last_error))
    return None if environment is None else MailboxStatus(environment, "environment")


async def put_box_mailbox(session: AsyncSession, vault: Vault, mailbox: Mailbox) -> None:
    """Keep the mailbox the box sends through, over the environment's; how it went is forgotten."""
    fields = {
        "host": mailbox.host,
        "port": mailbox.port,
        "security": mailbox.security,
        "username": mailbox.username,
        "sender": mailbox.sender,
    }
    await platform.put_setting(session, BOX_MAIL, fields, ciphertext=vault.seal(mailbox.password))


async def delete_box_mailbox(session: AsyncSession) -> bool:
    """Forget the box's stored mailbox, back to the environment's; whether one was stored."""
    return await platform.delete_setting(session, BOX_MAIL)


async def delete_org_mailbox(session: AsyncSession, org: str) -> bool:
    """Forget the org's own mailbox; whether it had one."""
    repository = MailRepository(session)
    row = await repository.get(org)
    if row is None:
        return False
    await repository.delete(row)
    return True


class Outbox:
    """Every email the gateway sends, through the org's mailbox or the box's, in the background."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], vault: Vault, box_mailbox: Mailbox | None) -> None:
        self.sessions = sessions
        self.vault = vault
        self.box_mailbox = box_mailbox
        self._in_flight: set[asyncio.Task[None]] = set()

    async def mailbox_for(self, org: str | None) -> MailboxStatus | None:
        """The org's mailbox, else the box's; with no org, only the box's."""
        async with self.sessions() as session:
            own = None if org is None else await get_org_mailbox(session, self.vault, org)
            return own or await get_box_mailbox(session, self.vault, self.box_mailbox)

    async def post(self, org: str | None, email: Email) -> bool:
        """Send in the background; False when nothing here can send it."""
        if await self.mailbox_for(org) is None:
            return False
        task = asyncio.create_task(self._posted(org, email))
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)
        return True

    async def send(self, org: str | None, email: Email) -> str | None:
        """Send and wait: None when it went, else the server's reply."""
        found = await self.mailbox_for(org)
        if found is None:
            return None
        try:
            if found.source == "org":
                await asyncio.to_thread(check_public, found.mailbox)
            await deliver(found.mailbox, email)
        except UpstreamError as refused:
            await self._record(org, found.source, str(refused))
            return str(refused)
        await self._record(org, found.source, None)
        logger.info("mailed %s through %s", email.subject, found.mailbox.host)
        return None

    async def drain(self) -> None:
        """Wait for every email in flight."""
        while self._in_flight:
            await asyncio.gather(*self._in_flight, return_exceptions=True)
            await asyncio.sleep(0)

    async def _posted(self, org: str | None, email: Email) -> None:
        error = await self.send(org, email)
        if error is not None:
            logger.warning("could not mail %s: %s", email.subject, error)

    # Kept on the mailbox the email went through: the org's row, or the box's stored one.
    async def _record(self, org: str | None, source: Source, error: str | None) -> None:
        if source == "stored":
            await self._record_box(error)
            return
        if source != "org" or org is None:
            return
        async with self.sessions() as session:
            repository = MailRepository(session)
            row = await repository.get(org)
            if row is not None:
                values: dict[str, object] = {"last_error": error}
                if error is None:
                    values["verified_at"] = now()
                await repository.update(row, **values)
            await session.commit()

    async def _record_box(self, error: str | None) -> None:
        async with self.sessions() as session:
            kept = await platform.get_sealed_setting(session, BOX_MAIL)
            if kept is None:
                return
            value, sealed = kept
            went: dict[str, object] = {"last_error": error}
            if error is None:
                went["verified_at"] = now().isoformat()
            await platform.put_setting(session, BOX_MAIL, {**value, **went}, ciphertext=sealed)
            await session.commit()


async def deliver(mailbox: Mailbox, email: Email, *, within_s: float = TIMEOUT_S) -> None:
    """Hand the email to the mail server; UpstreamError with its reply when it refuses."""
    message = EmailMessage()
    message["From"] = mailbox.sender
    message["To"] = email.to
    message["Subject"] = email.subject
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")
    try:
        await asyncio.wait_for(asyncio.to_thread(_hand_over, mailbox, message, within_s), within_s)
    except TimeoutError:
        raise UpstreamError(f"{mailbox.host}:{mailbox.port} did not answer in {within_s:g}s") from None


def check_public(mailbox: Mailbox) -> None:
    """Refuse an org's mailbox that is plain, or whose name resolves anywhere but the internet."""
    if mailbox.security == "none":
        raise UpstreamError("an org's mailbox is reached over TLS")
    try:
        addresses = dns.resolve(mailbox.host)
    except OSError:
        raise UpstreamError(f"{mailbox.host} resolves to no public address") from None
    if not dns.all_public(addresses):
        raise UpstreamError(f"{mailbox.host} resolves to no public address, or to one that is not")


def _hand_over(mailbox: Mailbox, message: EmailMessage, timeout: float) -> None:
    try:
        with _connect(mailbox, timeout) as server:
            if mailbox.security == "starttls":
                server.starttls(context=ssl.create_default_context())
            if mailbox.username:
                server.login(mailbox.username, mailbox.password)
            server.send_message(message)
    except smtplib.SMTPResponseException as refused:
        said = (
            refused.smtp_error.decode("utf-8", "replace")
            if isinstance(refused.smtp_error, bytes)
            else str(refused.smtp_error)
        )
        raise UpstreamError(
            f"{mailbox.host}:{mailbox.port} refused it: {refused.smtp_code} {said.strip()}"
        ) from refused
    except (OSError, smtplib.SMTPException) as down:
        raise UpstreamError(f"{mailbox.host}:{mailbox.port} did not answer: {type(down).__name__}: {down}") from down


def _connect(mailbox: Mailbox, timeout: float) -> smtplib.SMTP:
    if mailbox.security == "tls":
        return smtplib.SMTP_SSL(mailbox.host, mailbox.port, timeout=timeout, context=ssl.create_default_context())
    if mailbox.security == "none":
        # Resolved once and connected to by the address checked: a name cannot point elsewhere between.
        addresses = dns.resolve(mailbox.host)
        if not dns.all_private(addresses):
            raise UpstreamError(
                f"{mailbox.host} is not on this machine or a private network: a mailbox with no TLS reaches "
                f"only a relay there"
            )
        return smtplib.SMTP(str(addresses[0]), mailbox.port, timeout=timeout)
    return smtplib.SMTP(mailbox.host, mailbox.port, timeout=timeout)


def _security(word: str) -> Security:
    match word:
        case "starttls" | "tls" | "none":
            return word
        case _:
            raise ValidationError(f"a mailbox is secured by starttls, tls or none, not {word!r}")
