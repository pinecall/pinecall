"""The mailboxes an address of answers email: each read by one gateway at a time, its new emails heard as messages."""

import logging
from collections.abc import Awaitable, Callable

from runtime.exceptions import PinecallError
from runtime.kit.loops import survive
from runtime.live.parts import LiveParts
from runtime.live.service.whatsapp import Threads
from runtime.telephony import service as telephony

logger = logging.getLogger(__name__)

# How long a gateway holds a mailbox: a few passes, so another takes it up soon after this one is gone.
LEASED_FOR_S = 90.0
# What an email the event `mail.received` carries reads at most: the event is kept under 16 KB.
LONGEST_MAIL = 12000
MAIL_RECEIVED = "mail.received"

# The event is the flows' to keep, which stand above the live side: the gateway hands this in by name.
type SendMail = Callable[[telephony.MailReader, str, dict[str, object]], Awaitable[None]]


async def read_inboxes(live: LiveParts, threads: Threads, send_mail: SendMail) -> None:
    """One pass: every routed mailbox this gateway holds, or can take, is read, and each new email heard."""
    async with live.sessions.begin() as session_:
        mailboxes = await telephony.list_routed_mailboxes(session_, live.vault)
    for mailbox in mailboxes:
        with survive("reading a mailbox", mailbox.id):
            await read_inbox(live, threads, mailbox, send_mail)


# The cursor moves past an email once it was handed to its thread, whatever came of it: one email a
# thread cannot take is said and never read again (the claim of `read_once` holds it besides). A pass
# the server refused leaves the cursor where it was and says why on the mailbox's row.
async def read_inbox(live: LiveParts, threads: Threads, mailbox: telephony.EmailAccount, send_mail: SendMail) -> None:
    """Read one mailbox, when no other gateway does: its new emails heard, and where the reading stands kept."""
    async with live.sessions.begin() as session_:
        leased = await telephony.lease_inbox(session_, mailbox, by=live.owners.id, for_s=LEASED_FOR_S)
        reader = await telephony.find_mail_reader(session_, mailbox)
    if leased is None:
        return
    try:
        page = await telephony.read_new(mailbox.imap, leased.cursor)
    except PinecallError as refused:
        logger.warning("email: %s was not read: %s", mailbox.id, refused.message)
        async with live.sessions.begin() as session_:
            await telephony.move_inbox(session_, mailbox, leased.cursor, refused.message)
        return
    for uid, raw in page.messages:
        with survive("hearing an email", f"{mailbox.id} #{uid}"):
            fallback = f"<{page.cursor.uid_validity}.{uid}@{mailbox.id}>"
            if reader is not None:
                await _hand_to_app(reader, telephony.read_mail(raw, mailbox.id, fallback, LONGEST_MAIL), send_mail)
                continue
            inbound = telephony.read_email(raw, mailbox.id, fallback)
            if inbound is not None:
                await threads.receive(inbound)
    async with live.sessions.begin() as session_:
        await telephony.move_inbox(session_, mailbox, page.cursor, None)


# An address an app reads opens no conversation: each email is the app's event, which wakes the flows
# that wait on it (`app.on("mail.received", flow)` starts a run of it, once an email).
async def _hand_to_app(reader: telephony.MailReader, mail: telephony.Mail | None, send_mail: SendMail) -> None:
    if mail is None:
        return
    data: dict[str, object] = {
        "to": mail.to,
        "from": mail.sender,
        "from_name": mail.sender_name,
        "subject": mail.subject,
        "text": mail.text,
        "message_id": mail.message_id,
        "date": mail.date,
    }
    await send_mail(reader, MAIL_RECEIVED, data)
