"""A mailbox of the org's as an account: what its row seals, the address it answers at, how it sends."""

import pytest

from runtime.enums import Channel
from runtime.exceptions import ValidationError
from runtime.telephony.service.email_account import EmailAccount

BROUGHT = {
    "kind": "email",
    "address": "Help@Acme.example",
    "password": "imap-secret",
    "imap_host": "mail.acme.example",
    "smtp_host": "email-smtp.us-east-1.amazonaws.com",
    "smtp_port": 587,
    "smtp_username": "AKIAEXAMPLE",
    "smtp_password": "ses-secret",
    "sender_name": "Acme Help",
}


def test_a_mailbox_reads_as_it_is_brought_and_seals_what_it_read() -> None:
    """Its address lowercased, IMAP and SMTP apart, each with its login; the row reads back the same."""
    account = EmailAccount.read("org_1", BROUGHT, None)
    assert (account.id, account.login, account.imap.port) == ("help@acme.example", "help@acme.example", 993)
    outbox = account.outbox
    assert (outbox.host, outbox.port, outbox.security) == ("email-smtp.us-east-1.amazonaws.com", 587, "starttls")
    assert (outbox.username, outbox.password, outbox.sender) == (
        "AKIAEXAMPLE",
        "ses-secret",
        "Acme Help <help@acme.example>",
    )
    assert EmailAccount.read("org_1", account.dump()["account"], None) == account
    shown = account.describe()
    assert shown["smtp_host"] == "email-smtp.us-east-1.amazonaws.com" and shown["smtp_username"] == "AKIAEXAMPLE"
    assert "imap-secret" not in shown.values() and "ses-secret" not in shown.values(), (
        "a form is never shown a password"
    )


def test_smtp_logs_in_as_imap_when_no_relay_is_named_and_a_password_brought_again_keeps_the_relays() -> None:
    """One login for both by default, over TLS on 465; a relay's password survives a new IMAP password."""
    alone = EmailAccount.read("org_1", {**BROUGHT, "smtp_port": 465, "smtp_username": "", "smtp_password": ""}, None)
    assert (alone.outbox.username, alone.outbox.password, alone.outbox.security) == (
        "help@acme.example",
        "imap-secret",
        "tls",
    )
    was = EmailAccount.read("org_1", BROUGHT, None)
    again = EmailAccount.read("org_1", {**BROUGHT, "password": "new", "smtp_password": ""}, None).keep_from(was)
    assert (again.password, again.smtp_password) == ("new", "ses-secret")
    moved = EmailAccount.read("org_1", {**BROUGHT, "password": "", "smtp_host": "smtp.acme.example"}, None).keep_from(
        was
    )
    assert (moved.password, moved.smtp_password, moved.smtp_host) == ("imap-secret", "ses-secret", "smtp.acme.example")


async def test_a_mailbox_answers_email_at_its_own_address_and_nothing_else() -> None:
    """Another address, or the phone, is refused before anything is written."""
    account = EmailAccount.read("org_1", BROUGHT, None)
    await account.check_number(None, Channel.email, "help@acme.example")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="not the mailbox's address"):
        await account.check_number(None, Channel.email, "sales@acme.example")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="answers email, not phone"):
        await account.check_number(None, Channel.phone, "help@acme.example")  # type: ignore[arg-type]
    assert account.calling_networks() is None
