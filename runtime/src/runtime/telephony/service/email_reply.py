"""An agent's reply by email: set in the org's layout, threaded under the message it answers, and sent by SMTP."""

from email.utils import make_msgid

from runtime.mail import service as mail
from runtime.telephony.service.email_account import EmailAccount
from runtime.telephony.service.email_layout import set_in, text_of
from runtime.whatsapp import service as whatsapp

# What a reply's subject says when the email it answers had none.
NO_SUBJECT = "Your message"


def reply_subject(answered: str | None) -> str:
    """`Re:` and the subject answered, said once however long the thread."""
    said = (answered or NO_SUBJECT).strip() or NO_SUBJECT
    return said if said.lower().startswith(("re:", "aw:", "sv:")) else f"Re: {said}"


# Threaded as every client threads a reply (RFC 5322): `In-Reply-To` names the message answered and
# `References` the whole chain before it. `Auto-Submitted` (RFC 3834) tells another robot not to answer.
def compose_reply(account: EmailAccount, layout: str, answered: whatsapp.Inbound, text: str) -> mail.Email:
    """The reply as it goes out: to the contact, under the subject answered, as HTML in the layout and as text."""
    subject = reply_subject(answered.subject)
    chain = [*answered.references, answered.message_id]
    headers = {
        "Message-ID": make_msgid(domain=account.address.rsplit("@", 1)[-1]),
        "In-Reply-To": answered.message_id,
        "References": " ".join(dict.fromkeys(chain)),
        "Auto-Submitted": "auto-replied",
    }
    return mail.Email(
        to=answered.caller,
        subject=subject,
        text=text_of(text),
        html=set_in(layout, text, subject=subject),
        headers=headers,
    )


async def send_reply(account: EmailAccount, email: mail.Email) -> None:
    """Hand the reply to the mailbox's SMTP server; UpstreamError in its words when it refuses."""
    mail.check_public(account.outbox)
    await mail.deliver(account.outbox, email)
