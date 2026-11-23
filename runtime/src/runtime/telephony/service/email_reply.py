"""An agent's email: the first of a thread it writes, or a reply threaded under what it answers, in the org's layout."""

from email.utils import make_msgid

from runtime.mail import service as mail
from runtime.telephony.service.email_account import EmailAccount
from runtime.telephony.service.email_layout import Layout, set_in, text_of
from runtime.whatsapp import service as whatsapp

# What a reply's subject says when the email it answers had none.
NO_SUBJECT = "Your message"


def reply_subject(answered: str | None) -> str:
    """`Re:` and the subject answered, said once however long the thread."""
    said = (answered or NO_SUBJECT).strip() or NO_SUBJECT
    return said if said.lower().startswith(("re:", "aw:", "sv:")) else f"Re: {said}"


def new_message_id(address: str) -> str:
    """A fresh `Message-ID` of the address's domain."""
    return make_msgid(domain=address.rsplit("@", 1)[-1])


# Threaded as every client threads a reply (RFC 5322): `In-Reply-To` names the message answered and
# `References` the whole chain before it. `Auto-Submitted` (RFC 3834) tells another robot not to answer.
def compose_reply(account: EmailAccount, layout: Layout, answered: whatsapp.Inbound, text: str) -> mail.Email:
    """The reply as it goes out: to the contact, under the subject answered, as text and as HTML in the org's layout."""
    chain = [*answered.references, answered.message_id]
    headers = {
        "Message-ID": new_message_id(account.address),
        "In-Reply-To": answered.message_id,
        "References": " ".join(dict.fromkeys(chain)),
        "Auto-Submitted": "auto-replied",
    }
    return _composed(layout, answered.caller, reply_subject(answered.subject), text, headers)


# The thread's first message, under the id its thread was opened by (`to.thread`): the contact's reply
# names it in `In-Reply-To` and `References`, which lands that reply on the same thread. It answers
# nothing, so it is not `auto-replied`: RFC 3834 §5 calls a message an automatic process wrote that
# is no direct response to another `auto-generated`, and a contact's autoresponder still keeps from
# answering it (§2).
def compose_first(layout: Layout, to: whatsapp.Inbound, text: str) -> mail.Email:
    """The first email of a thread the agent opens: to the contact, under the thread's subject and its id."""
    headers = {"Message-ID": to.thread, "Auto-Submitted": "auto-generated"}
    return _composed(layout, to.caller, (to.subject or "").strip() or NO_SUBJECT, text, headers)


async def send_email(account: EmailAccount, email: mail.Email) -> None:
    """Hand the email to the mailbox's SMTP server; UpstreamError in its words when it refuses."""
    mail.check_public(account.outbox)
    await mail.deliver(account.outbox, email)


def _composed(layout: Layout, to: str, subject: str, text: str, headers: dict[str, str]) -> mail.Email:
    return mail.Email(
        to=to,
        subject=subject,
        text=text_of(text),
        html=None if layout.text_only else set_in(layout.html, text, subject=subject),
        headers=headers,
    )
