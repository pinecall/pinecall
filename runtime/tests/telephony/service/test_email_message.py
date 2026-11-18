"""An email as the agent reads it: its writer, its thread, its own words; and the emails nobody answers."""

from email.message import EmailMessage

import pytest

from runtime.enums import Channel
from runtime.telephony.service import email_message

MAILBOX = "help@acme.example"
FALLBACK = "<1.7@help@acme.example>"


def an_email(text: str = "Hola, ¿abren el sábado?", **headers: str) -> bytes:
    """An email to the mailbox, from Ana, with the headers given over the usual ones."""
    message = EmailMessage()
    usual = {
        "From": "Ana Pérez <Ana@Example.org>",
        "To": MAILBOX,
        "Subject": "Horarios",
        "Message-ID": "<a1@example.org>",
    }
    for name, value in {**usual, **headers}.items():
        if value:
            message[name] = value
    message.set_content(text)
    return message.as_bytes()


def test_an_email_is_a_message_of_its_own_thread_from_its_writer() -> None:
    """The writer's address lowercased, their name, the subject, the id, and the thread it opens."""
    read = email_message.read_email(an_email(), MAILBOX, FALLBACK)
    assert read is not None
    assert (read.channel, read.number, read.caller, read.name) == (
        Channel.email,
        MAILBOX,
        "ana@example.org",
        "Ana Pérez",
    )
    assert (read.subject, read.message_id, read.references, read.thread) == (
        "Horarios",
        "<a1@example.org>",
        (),
        "<a1@example.org>",
    )
    assert read.text == "Hola, ¿abren el sábado?"


def test_a_reply_belongs_to_the_thread_its_first_message_opened_and_says_its_own_words_alone() -> None:
    """The thread is the first id of References; the quoted past and the signature are cut."""
    written = (
        "Perfecto, el sábado a las 10.\n\n-- \nAna\n\n"
        "On Tue, Nov 18, 2026 at 9:00 AM Help <help@acme.example> wrote:\n> ¿Le sirve el sábado?"
    )
    raw = an_email(written, **{"Message-ID": "<a3@example.org>", "References": "<a1@example.org> <r2@acme.example>"})
    read = email_message.read_email(raw, MAILBOX, FALLBACK)
    assert read is not None
    assert (read.thread, read.references, read.text) == (
        "<a1@example.org>",
        ("<a1@example.org>", "<r2@acme.example>"),
        "Perfecto, el sábado a las 10.",
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"From": "help@acme.example"},
        {"From": "MAILER-DAEMON@mx.example.org"},
        {"From": "no-reply@shop.example"},
        {"Auto-Submitted": "auto-replied"},
        {"Precedence": "bulk"},
        {"List-Id": "<news.example.org>"},
    ],
)
def test_an_email_no_person_wrote_or_the_mailbox_itself_sent_is_not_answered(headers: dict[str, str]) -> None:
    """A loop, a bounce, a robot, a list: read, and nothing comes of it."""
    assert email_message.read_email(an_email(**headers), MAILBOX, FALLBACK) is None


def test_an_email_with_html_alone_is_read_as_its_words_and_one_with_no_id_takes_the_fallback() -> None:
    """Styles and scripts left out, a line a block; the id the inbox's UID makes when the email had none."""
    message = EmailMessage()
    message["From"] = "ana@example.org"
    message["To"] = MAILBOX
    message.set_content(
        "<html><head><style>p{}</style></head><body><p>Hola</p><p>¿Abren?</p></body></html>", subtype="html"
    )
    read = email_message.read_email(message.as_bytes(), MAILBOX, FALLBACK)
    assert read is not None
    assert (read.text, read.message_id, read.subject) == ("Hola\n\n¿Abren?", FALLBACK, None)
