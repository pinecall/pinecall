"""An agent's reply by email: under the subject it answers, threaded under that message, set in the layout."""

from runtime.enums import Channel
from runtime.telephony.service import email_reply
from runtime.telephony.service.email_account import EmailAccount
from runtime.telephony.service.email_layout import PLAIN, Layout
from runtime.whatsapp.service.webhook import Inbound

THE_PLAIN_ONE = Layout(PLAIN, own=False)
ACCOUNT = EmailAccount(
    org="org_1", address="help@acme.example", password="p", imap_host="mail.acme.example", smtp_host="mail.acme.example"
)


def answered(subject: str | None, references: tuple[str, ...] = ()) -> Inbound:
    """Ana's email to the mailbox, on a subject, after the messages named."""
    return Inbound(
        number="help@acme.example",
        phone_number_id="help@acme.example",
        wa_id="ana@example.org",
        name="Ana",
        message_id="<a3@example.org>",
        kind="text",
        text="¿Abren el sábado?",
        channel=Channel.email,
        subject=subject,
        references=references,
        thread=(references or ("<a3@example.org>",))[0],
    )


def test_a_reply_goes_to_its_writer_under_re_once_and_threaded_under_what_it_answers() -> None:
    """`Re:` said once however long the thread; In-Reply-To the message; References the chain and it."""
    email = email_reply.compose_reply(
        ACCOUNT, THE_PLAIN_ONE, answered("Re: Horarios", ("<a1@example.org>",)), "**Sí**, de 10 a 14."
    )
    assert (email.to, email.subject) == ("ana@example.org", "Re: Horarios")
    assert email.headers["In-Reply-To"] == "<a3@example.org>"
    assert email.headers["References"] == "<a1@example.org> <a3@example.org>"
    assert email.headers["Auto-Submitted"] == "auto-replied"
    assert email.headers["Message-ID"].endswith("@acme.example>")
    assert email.html is not None and "<strong>Sí</strong>, de 10 a 14." in email.html
    assert email.text == "Sí, de 10 a 14."


def test_an_org_that_sends_text_alone_gets_no_html_part_and_the_same_threading() -> None:
    """No template at all: the words, their marks taken off, and nothing set in any HTML."""
    as_text = Layout(PLAIN, own=True, text_only=True)
    email = email_reply.compose_reply(
        ACCOUNT, as_text, answered("Horarios"), "**Sí**, [reservá](https://acme.example)."
    )
    assert email.html is None and email.text == "Sí, reservá (https://acme.example)."
    assert (email.subject, email.headers["In-Reply-To"]) == ("Re: Horarios", "<a3@example.org>")


def test_an_email_with_no_subject_is_answered_under_one_of_ours() -> None:
    """The subject the reply's says when the email had none."""
    assert email_reply.compose_reply(ACCOUNT, THE_PLAIN_ONE, answered(None), "Hola").subject == "Re: Your message"
    assert email_reply.reply_subject("AW: Termin") == "AW: Termin"
