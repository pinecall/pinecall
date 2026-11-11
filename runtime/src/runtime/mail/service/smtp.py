"""An email handed to a mail server over SMTP, and the check that an org's server is on the internet."""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from runtime.exceptions import UpstreamError
from runtime.kit import dns
from runtime.mail.service.emails import Email
from runtime.mail.service.mailboxes import Mailbox

TIMEOUT_S = 10.0


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
