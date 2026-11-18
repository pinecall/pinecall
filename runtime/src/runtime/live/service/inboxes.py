"""The mailboxes an address of answers email: each read by one gateway at a time, its new emails heard as messages."""

import logging

from runtime.exceptions import PinecallError
from runtime.kit.loops import survive
from runtime.live.parts import LiveParts
from runtime.live.service.whatsapp import Threads
from runtime.telephony import service as telephony

logger = logging.getLogger(__name__)

# How long a gateway holds a mailbox: a few passes, so another takes it up soon after this one is gone.
LEASED_FOR_S = 90.0


async def read_inboxes(live: LiveParts, threads: Threads) -> None:
    """One pass: every routed mailbox this gateway holds, or can take, is read, and each new email heard."""
    async with live.sessions.begin() as session_:
        mailboxes = await telephony.list_routed_mailboxes(session_, live.vault)
    for mailbox in mailboxes:
        with survive("reading a mailbox", mailbox.id):
            await read_inbox(live, threads, mailbox)


# The cursor moves past an email once it was handed to its thread, whatever came of it: one email a
# thread cannot take is said and never read again (the claim of `read_once` holds it besides). A pass
# the server refused leaves the cursor where it was and says why on the mailbox's row.
async def read_inbox(live: LiveParts, threads: Threads, mailbox: telephony.EmailAccount) -> None:
    """Read one mailbox, when no other gateway does: its new emails heard, and where the reading stands kept."""
    async with live.sessions.begin() as session_:
        leased = await telephony.lease_inbox(session_, mailbox, by=live.owners.id, for_s=LEASED_FOR_S)
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
            inbound = telephony.read_email(raw, mailbox.id, fallback)
            if inbound is not None:
                await threads.receive(inbound)
    async with live.sessions.begin() as session_:
        await telephony.move_inbox(session_, mailbox, page.cursor, None)
