"""The mailboxes an address of answers email: read by one gateway at a time, each new email heard on its thread."""

import secrets

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.enums import Channel, Env
from runtime.exceptions import UpstreamError
from runtime.live.peers import ThreadKey
from runtime.live.service import inboxes
from runtime.live.service.whatsapp import _thread_key  # pyright: ignore[reportPrivateUsage]
from runtime.telephony import service as telephony
from runtime.telephony.repository import EmailInboxRepository, RouteRepository, RouteToWrite
from runtime.telephony.service import accounts
from runtime.telephony.service.email_account import EmailAccount
from runtime.telephony.service.email_box import Cursor, ImapServer, Page
from runtime.whatsapp.service.webhook import Inbound
from tests.conftest import Tenant, needs_the_database
from tests.live.conftest import Side
from tests.telephony.service.test_email_message import an_email


@pytest.fixture
async def mailbox(side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant) -> EmailAccount:
    """A mailbox of the tenant's whose address answers email for agent front-desk in the sandbox."""
    address = f"help-{secrets.token_hex(3)}@acme.example"
    account = EmailAccount(
        org=tenant.org, address=address, password="p", imap_host="mail.acme.example", smtp_host="mail.acme.example"
    )
    route = RouteToWrite(
        org=tenant.org, number=address, agent="front-desk", channel=Channel.email, env=Env.sandbox, account=address
    )
    async with sessions.begin() as session:
        await accounts.put_carrier(session, side.parts.vault, account)
        await RouteRepository(session).put(route)
    return account


@needs_the_database
async def test_a_routed_mailbox_is_read_by_one_gateway_and_each_new_email_reaches_its_thread(
    side: Side, sessions: async_sessionmaker[AsyncSession], mailbox: EmailAccount, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its new emails heard, robots' dropped, the cursor kept; another gateway's lease leaves it alone."""
    asked: list[Cursor] = []
    heard: list[Inbound] = []

    async def read_new(server: ImapServer, cursor: Cursor) -> Page:
        asked.append(cursor)
        return Page(
            ((5, an_email(To=mailbox.address)), (6, an_email(To=mailbox.address, Precedence="bulk"))), Cursor(7, 6)
        )

    async def receive(inbound: Inbound) -> bool:
        heard.append(inbound)
        return True

    monkeypatch.setattr(telephony, "read_new", read_new)
    monkeypatch.setattr(side.threads, "receive", receive)
    async with sessions() as session:
        assert mailbox.id in [found.id for found in await telephony.list_routed_mailboxes(session, side.parts.vault)]
    await inboxes.read_inbox(side.parts, side.threads, mailbox)
    assert (asked, [message.caller for message in heard]) == ([Cursor()], ["ana@example.org"])
    async with sessions() as session:
        leased = await telephony.lease_inbox(session, mailbox, by="another-gateway", for_s=60)
    assert leased is None, "this gateway's lease runs"
    await inboxes.read_inbox(side.parts, side.threads, mailbox)
    assert asked[-1] == Cursor(7, 6), "the next pass starts where the last stopped"


@needs_the_database
async def test_a_mailbox_the_server_refuses_keeps_its_cursor_and_says_why(
    side: Side, sessions: async_sessionmaker[AsyncSession], mailbox: EmailAccount, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A login refused is a line on the mailbox's row; the next pass tries from the same place."""

    async def read_new(server: ImapServer, cursor: Cursor) -> Page:
        raise UpstreamError("mail.acme.example:993 refused the login: AUTHENTICATIONFAILED")

    monkeypatch.setattr(telephony, "read_new", read_new)
    await inboxes.read_inbox(side.parts, side.threads, mailbox)
    async with sessions() as session:
        row = await EmailInboxRepository(session).one(
            EmailInboxRepository(session)
            .statement()
            .where(EmailInboxRepository.model.org == mailbox.org, EmailInboxRepository.model.account == mailbox.id)
        )
    assert (row.last_uid, row.last_error) == (None, "mail.acme.example:993 refused the login: AUTHENTICATIONFAILED")


def test_one_contacts_emails_on_two_subjects_are_two_threads() -> None:
    """The thread's first id is in its key: a second subject is a second conversation, and a reply joins the first."""
    scope = Scope("org_1", Env.sandbox)
    first = Inbound(
        "help@acme.example", "x", "ana@example.org", None, "<a1@x>", "text", "a", channel=Channel.email, thread="<a1@x>"
    )
    other = Inbound(
        "help@acme.example", "x", "ana@example.org", None, "<b1@x>", "text", "b", channel=Channel.email, thread="<b1@x>"
    )
    reply = Inbound(
        "help@acme.example", "x", "ana@example.org", None, "<a3@x>", "text", "c", channel=Channel.email, thread="<a1@x>"
    )
    keys = {_thread_key(scope, message) for message in (first, other, reply)}
    assert keys == {
        ThreadKey("org_1", Env.sandbox, "help@acme.example", "ana@example.org", Channel.email, "<a1@x>"),
        ThreadKey("org_1", Env.sandbox, "help@acme.example", "ana@example.org", Channel.email, "<b1@x>"),
    }
    assert str(ThreadKey("o", Env.sandbox, "+1", "2")) == "o|sandbox|+1|2", "a WhatsApp thread's name is as it was"
