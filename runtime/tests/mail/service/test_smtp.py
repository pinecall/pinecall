"""An email handed to a mail server over SMTP: what it carries as it arrives."""

from email.utils import parsedate_to_datetime

from runtime.kit.time import now
from runtime.mail.service import smtp
from runtime.mail.service.emails import Email
from tests.fakes.smtp import Relay


# Maddy added the missing header itself (2026-11-23, "submission: adding missing Date header"); a
# stricter relay refuses the email or scores it as spam.
async def test_every_email_is_dated_when_it_is_handed_over_as_rfc_5322_requires() -> None:
    async with Relay() as relay:
        await smtp.deliver(relay.mailbox, Email(to="ana@example.org", subject="Hola", text="Hola", html=None))
    (taken,) = relay.to("ana@example.org")
    dated = parsedate_to_datetime(str(taken["Date"]))
    assert abs((now() - dated).total_seconds()) < 60
