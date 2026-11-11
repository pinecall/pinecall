"""The outbox: every email the gateway sends, through the org's mailbox or the box's, in the background."""

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.exceptions import Conflict, UpstreamError
from runtime.kit.crypto import Vault
from runtime.kit.tasks import Tasks
from runtime.mail.service.emails import Email, test_email
from runtime.mail.service.mailboxes import (
    Mailbox,
    MailboxStatus,
    address_of,
    find_box_mailbox,
    find_org_mailbox,
    record_box_delivery,
    record_org_delivery,
)
from runtime.mail.service.smtp import check_public, deliver
from runtime.platform import service as platform

logger = logging.getLogger(__name__)

NO_ORG_MAIL = (
    "neither this org nor this box has a mail server: set one at PUT /v1/org/mail, or PINECALL_SMTP_URL on the box"
)
NO_BOX_MAIL = "this box has no mail server: set one at PUT /v1/ops/mail, or set PINECALL_SMTP_URL"


class NoMailbox(Conflict):
    """Nothing here can send an email: neither the org nor the box has a mail server."""

    def __init__(self, org: str | None) -> None:
        super().__init__(NO_BOX_MAIL if org is None else NO_ORG_MAIL)


@dataclass(frozen=True, slots=True)
class Delivery:
    """How one email that was waited for went: taken, or what the server said."""

    sent: bool
    error: str | None


class Outbox:
    """Every email the gateway sends, through the org's mailbox or the box's, in the background."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], vault: Vault, box_mailbox: Mailbox | None) -> None:
        self.sessions = sessions
        self.vault = vault
        self.box_mailbox = box_mailbox
        self._in_flight = Tasks("the outbox")

    async def mailbox_for(self, org: str | None) -> MailboxStatus | None:
        """The org's mailbox, else the box's; with no org, only the box's."""
        async with self.sessions() as session:
            own = None if org is None else await find_org_mailbox(session, self.vault, org)
            return own or await find_box_mailbox(session, self.vault, self.box_mailbox)

    async def post(self, org: str | None, email: Email) -> bool:
        """Send in the background; False when nothing here can send it."""
        if await self.mailbox_for(org) is None:
            return False
        self._in_flight.spawn(self._send_and_say(org, email), name=f"email {email.subject}")
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
            await self._record(org, found, str(refused))
            return str(refused)
        await self._record(org, found, None)
        logger.info("mailed %s through %s", email.subject, found.mailbox.host)
        return None

    # The one email a person waits for: they are watching, and read what the server said.
    async def send_test(self, org: str | None, to: str, brand: platform.Brand) -> Delivery:
        """One test email through the org's mailbox (the box's with no org), waited for; NoMailbox with none."""
        if await self.mailbox_for(org) is None:
            raise NoMailbox(org)
        error = await self.send(org, test_email(address_of(to), brand))
        return Delivery(sent=error is None, error=error)

    async def drain(self) -> None:
        """Wait for every email in flight."""
        while len(self._in_flight):
            await asyncio.sleep(0.05)

    async def _send_and_say(self, org: str | None, email: Email) -> None:
        error = await self.send(org, email)
        if error is not None:
            logger.warning("could not mail %s: %s", email.subject, error)

    # In a transaction of its own: how an email went is kept whatever the request that sent it does next.
    async def _record(self, org: str | None, found: MailboxStatus, error: str | None) -> None:
        async with self.sessions.begin() as session:
            if found.source == "stored":
                await record_box_delivery(session, error)
            elif found.source == "org" and org is not None:
                await record_org_delivery(session, org, error)
